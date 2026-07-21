"use client";

import { useCallback, useEffect, useState } from "react";
import { Shield, Users } from "lucide-react";
import { useSession } from "next-auth/react";

import LoadingCards from "@/components/LoadingCards";
import {
  ApiError,
  fetchAdminConfig,
  fetchAdminOperators,
  updateAdminApprovalRule,
  updateAdminConfig,
  updateAdminOperator,
} from "@/lib/api";
import { formatTimestamp } from "@/lib/format";
import type { AdminConfig, ApprovalRule, OperatorAccount, OperatorRole } from "@/lib/types";

const ROLES: OperatorRole[] = ["operator", "reviewer", "admin"];

function roleLabel(role: OperatorRole): string {
  if (role === "admin") return "Admin";
  if (role === "reviewer") return "Reviewer";
  return "Operator";
}

function categoryLabel(category: string): string {
  return category.replace(/_/g, " ");
}

function EditableConfigRow({
  label,
  configKey,
  currentValue,
  saving,
  success,
  error,
  onSave,
  options,
  hint,
}: {
  label: string;
  configKey: string;
  currentValue: string;
  saving: string | null;
  success: string | null;
  error?: string;
  onSave: (key: string, value: string) => Promise<void>;
  options?: string[];
  hint?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(currentValue);
  const isSaving = saving === configKey;
  const isSuccess = success === configKey;

  function handleEdit() {
    setDraft(currentValue);
    setEditing(true);
  }

  function handleCancel() {
    setEditing(false);
    setDraft(currentValue);
  }

  async function handleSave() {
    await onSave(configKey, draft);
    setEditing(false);
  }

  return (
    <div className="mb-3 rounded-control border border-white/10 bg-white/[0.02] px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <dt className="text-[11px] uppercase tracking-wide text-slate-500">
          {label}
        </dt>
        {!editing && (
          <button
            type="button"
            onClick={handleEdit}
            className="text-[10px] font-medium text-accent-primary hover:underline"
          >
            Edit
          </button>
        )}
      </div>
      {editing ? (
        <div className="mt-1 flex items-center gap-2">
          {options ? (
            <select
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="rounded-control border border-white/10 bg-surface px-2 py-1 text-sm text-slate-100"
            >
              {options.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}
                </option>
              ))}
            </select>
          ) : (
            <input
              type="text"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              className="flex-1 rounded-control border border-white/10 bg-surface px-2 py-1 text-sm text-slate-100"
              placeholder="Enter value…"
            />
          )}
          <button
            type="button"
            disabled={isSaving}
            onClick={() => void handleSave()}
            className="rounded-control border border-accent-green/30 bg-accent-green/10 px-2 py-1 text-[10px] font-semibold text-accent-green disabled:opacity-50"
          >
            {isSaving ? "…" : "Save"}
          </button>
          <button
            type="button"
            onClick={handleCancel}
            className="rounded-control border border-white/10 px-2 py-1 text-[10px] font-semibold text-slate-400"
          >
            Cancel
          </button>
        </div>
      ) : (
        <dd className="mt-1 text-sm text-slate-100">
          {currentValue || "—"}
          {isSuccess && (
            <span className="ml-2 text-[10px] font-medium text-accent-green">
              Saved
            </span>
          )}
        </dd>
      )}
      {hint && !editing && (
        <p className="mt-0.5 text-[10px] text-slate-600">{hint}</p>
      )}
      {error && <p className="mt-1 text-xs text-red-300">{error}</p>}
    </div>
  );
}

function EditableApprovalRuleRow({
  rule,
  saving,
  success,
  error,
  onSave,
}: {
  rule: ApprovalRule;
  saving: string | null;
  success: string | null;
  error?: string;
  onSave: (agentName: string, statuses: string[]) => Promise<void>;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(rule.risky_statuses.join(", "));
  const isSaving = saving === rule.agent_name;
  const isSuccess = success === rule.agent_name;

  async function handleSave() {
    const statuses = draft
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
    await onSave(rule.agent_name, statuses);
    setEditing(false);
  }

  return (
    <div className="mb-3 rounded-control border border-white/10 bg-white/[0.02] px-3 py-2">
      <div className="flex items-center justify-between gap-2">
        <dt className="font-mono text-[11px] uppercase tracking-wide text-slate-500">
          {rule.agent_name}
        </dt>
        {!editing && (
          <button
            type="button"
            onClick={() => {
              setDraft(rule.risky_statuses.join(", "));
              setEditing(true);
            }}
            className="text-[10px] font-medium text-accent-primary hover:underline"
          >
            Edit
          </button>
        )}
      </div>
      {editing ? (
        <div className="mt-1 flex items-center gap-2">
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            placeholder="SEND_REMINDER, ESCALATE"
            className="flex-1 rounded-control border border-white/10 bg-surface px-2 py-1 text-sm text-slate-100"
          />
          <button
            type="button"
            disabled={isSaving}
            onClick={() => void handleSave()}
            className="rounded-control border border-accent-green/30 bg-accent-green/10 px-2 py-1 text-[10px] font-semibold text-accent-green disabled:opacity-50"
          >
            {isSaving ? "…" : "Save"}
          </button>
          <button
            type="button"
            onClick={() => setEditing(false)}
            className="rounded-control border border-white/10 px-2 py-1 text-[10px] font-semibold text-slate-400"
          >
            Cancel
          </button>
        </div>
      ) : (
        <dd className="mt-1 text-sm text-slate-100">
          {rule.risky_statuses.join(", ") || "—"}
          {isSuccess && (
            <span className="ml-2 text-[10px] font-medium text-accent-green">
              Saved
            </span>
          )}
        </dd>
      )}
      {error && <p className="mt-1 text-xs text-red-300">{error}</p>}
    </div>
  );
}

/** Admin panel — operator roles and editable routing/approval config. */
export default function AdminPage() {
  const { data: session } = useSession();
  const [role, setRole] = useState<OperatorRole | null>(
    session?.user?.role ?? null,
  );
  const [operators, setOperators] = useState<OperatorAccount[]>([]);
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [rowLoading, setRowLoading] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});
  const [configSaving, setConfigSaving] = useState<string | null>(null);
  const [configSuccess, setConfigSuccess] = useState<string | null>(null);
  const [ruleSaving, setRuleSaving] = useState<string | null>(null);
  const [ruleSuccess, setRuleSuccess] = useState<string | null>(null);

  useEffect(() => {
    if (session?.user?.role) {
      setRole(session.user.role);
      return;
    }
    let cancelled = false;
    fetch("/api/auth/me", { credentials: "same-origin" })
      .then(async (response) => {
        if (!response.ok) return null;
        return (await response.json()) as { role?: OperatorRole };
      })
      .then((data) => {
        if (!cancelled && data?.role) setRole(data.role);
      })
      .catch(() => {
        if (!cancelled) setRole(null);
      });
    return () => {
      cancelled = true;
    };
  }, [session]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [operatorRows, configPayload] = await Promise.all([
        fetchAdminOperators(),
        fetchAdminConfig(),
      ]);
      setOperators(operatorRows);
      setConfig(configPayload);
    } catch (err) {
      const message =
        err instanceof ApiError && err.status === 403
          ? "Admin access required."
          : err instanceof Error
            ? err.message
            : "Failed to load admin settings.";
      setError(message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (role === "admin") {
      void load();
    } else if (role !== null) {
      setLoading(false);
    }
  }, [load, role]);

  async function handleRoleChange(
    email: string,
    nextRole: OperatorRole,
  ): Promise<void> {
    setRowLoading(email);
    setRowErrors((prev) => {
      const next = { ...prev };
      delete next[email];
      return next;
    });
    try {
      const updated = await updateAdminOperator(email, { role: nextRole });
      setOperators((prev) =>
        prev.map((row) => (row.email === email ? updated : row)),
      );
    } catch (err) {
      setRowErrors((prev) => ({
        ...prev,
        [email]:
          err instanceof Error ? err.message : "Failed to update operator role.",
      }));
    } finally {
      setRowLoading(null);
    }
  }

  async function handleActiveToggle(
    email: string,
    active: boolean,
  ): Promise<void> {
    setRowLoading(email);
    setRowErrors((prev) => {
      const next = { ...prev };
      delete next[email];
      return next;
    });
    try {
      const updated = await updateAdminOperator(email, { active });
      setOperators((prev) =>
        prev.map((row) => (row.email === email ? updated : row)),
      );
    } catch (err) {
      setRowErrors((prev) => ({
        ...prev,
        [email]:
          err instanceof Error
            ? err.message
            : "Failed to update operator status.",
      }));
    } finally {
      setRowLoading(null);
    }
  }

  async function handleApprovalRuleSave(
    agentName: string,
    statuses: string[],
  ): Promise<void> {
    setRuleSaving(agentName);
    setRuleSuccess(null);
    try {
      await updateAdminApprovalRule(agentName, statuses);
      setRuleSuccess(agentName);
      void load();
      setTimeout(() => setRuleSuccess(null), 2000);
    } catch (err) {
      setRowErrors((prev) => ({
        ...prev,
        [`rule:${agentName}`]:
          err instanceof Error ? err.message : "Failed to save approval rule.",
      }));
    } finally {
      setRuleSaving(null);
    }
  }

  async function handleConfigSave(key: string, value: string): Promise<void> {
    setConfigSaving(key);
    setConfigSuccess(null);
    try {
      await updateAdminConfig(key, value);
      setConfigSuccess(key);
      void load(); // refresh resolved config
      setTimeout(() => setConfigSuccess(null), 2000);
    } catch (err) {
      setRowErrors((prev) => ({
        ...prev,
        [`cfg:${key}`]:
          err instanceof Error ? err.message : "Failed to save config.",
      }));
    } finally {
      setConfigSaving(null);
    }
  }

  if (role !== null && role !== "admin") {
    return (
      <div className="page-shell">
        <header className="mb-8">
          <p className="page-eyebrow">Administration</p>
          <h1 className="page-title">Access denied</h1>
          <p className="page-lead">
            Only admins can manage operator roles and routing settings.
          </p>
        </header>
      </div>
    );
  }

  return (
    <div className="page-shell">
      <header className="mb-8">
        <p className="page-eyebrow">Administration</p>
        <h1 className="page-title">Admin Settings</h1>
        <p className="page-lead">
          Manage operator roles and review routing owners and approval rules.
        </p>
      </header>

      {loading && <LoadingCards count={2} />}

      {!loading && error && (
        <div className="rounded-card border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-200">
          {error}
        </div>
      )}

      {!loading && !error && (
        <div className="space-y-8">
          <section className="rounded-card border border-white/10 bg-surface-raised/40 p-5">
            <div className="mb-4 flex items-center gap-2">
              <Users className="h-4 w-4 text-accent-primary" aria-hidden />
              <h2 className="text-sm font-semibold text-slate-100">
                Operator accounts
              </h2>
            </div>
            <div className="overflow-x-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="text-[11px] uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="px-3 py-2 font-semibold">Operator</th>
                    <th className="px-3 py-2 font-semibold">Role</th>
                    <th className="px-3 py-2 font-semibold">Status</th>
                    <th className="px-3 py-2 font-semibold">Last login</th>
                  </tr>
                </thead>
                <tbody>
                  {operators.map((operator) => (
                    <tr
                      key={operator.email}
                      className="border-t border-white/5 text-slate-200"
                    >
                      <td className="px-3 py-3">
                        <p className="font-medium">{operator.display_name || "—"}</p>
                        <p className="text-xs text-slate-500">{operator.email}</p>
                        {rowErrors[operator.email] && (
                          <p className="mt-1 text-xs text-red-300">
                            {rowErrors[operator.email]}
                          </p>
                        )}
                      </td>
                      <td className="px-3 py-3">
                        <select
                          value={operator.role}
                          disabled={rowLoading === operator.email}
                          onChange={(event) =>
                            void handleRoleChange(
                              operator.email,
                              event.target.value as OperatorRole,
                            )
                          }
                          className="rounded-control border border-white/10 bg-surface px-2 py-1.5 text-sm text-slate-100"
                        >
                          {ROLES.map((value) => (
                            <option key={value} value={value}>
                              {roleLabel(value)}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className="px-3 py-3">
                        <label className="inline-flex items-center gap-2 text-xs text-slate-400">
                          <input
                            type="checkbox"
                            checked={operator.active}
                            disabled={rowLoading === operator.email}
                            onChange={(event) =>
                              void handleActiveToggle(
                                operator.email,
                                event.target.checked,
                              )
                            }
                            className="rounded border-white/20 bg-surface"
                          />
                          {operator.active ? "Active" : "Disabled"}
                        </label>
                      </td>
                      <td className="px-3 py-3 text-xs text-slate-500">
                        {operator.last_login_at
                          ? formatTimestamp(operator.last_login_at)
                          : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {config && (
            <section className="rounded-card border border-white/10 bg-surface-raised/40 p-5">
              <div className="mb-4 flex items-center gap-2">
                <Shield className="h-4 w-4 text-accent-primary" aria-hidden />
                <h2 className="text-sm font-semibold text-slate-100">
                  Routing and approval policy
                </h2>
              </div>
              <p className="mb-4 text-xs text-slate-500">
                Changes are saved to the database immediately and take effect
                on the next agent run — no redeploy needed.
              </p>

              <EditableConfigRow
                label="Write-back mode"
                configKey="write_back_mode"
                currentValue={config.write_back_mode || "dry_run"}
                saving={configSaving}
                success={configSuccess}
                error={rowErrors["cfg:write_back_mode"]}
                onSave={handleConfigSave}
                options={["dry_run", "live"]}
              />
              <EditableConfigRow
                label="Default owner email"
                configKey="notify_owner_email"
                currentValue={config.notify_owner_email}
                saving={configSaving}
                success={configSuccess}
                error={rowErrors["cfg:notify_owner_email"]}
                onSave={handleConfigSave}
              />
              <EditableConfigRow
                label="Follow-up notify email"
                configKey="followup_notify_email"
                currentValue={config.followup_notify_email}
                saving={configSaving}
                success={configSuccess}
                error={rowErrors["cfg:followup_notify_email"]}
                onSave={handleConfigSave}
              />

              <h3 className="mb-2 mt-6 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Intake category owners
              </h3>
              {config.category_owners.map((owner) => (
                <EditableConfigRow
                  key={owner.category}
                  label={categoryLabel(owner.category)}
                  configKey={`intake_${owner.category}_owner_email`}
                  currentValue={owner.email}
                  saving={configSaving}
                  success={configSuccess}
                  error={rowErrors[`cfg:intake_${owner.category}_owner_email`]}
                  onSave={handleConfigSave}
                  hint={`Source: ${owner.source}`}
                />
              ))}

              <h3 className="mb-2 mt-6 text-xs font-semibold uppercase tracking-wide text-slate-500">
                Human approval rules
              </h3>
              <p className="mb-3 text-xs text-slate-500">
                Results below the confidence threshold or with a listed risky
                status require reviewer approval before write-back.
              </p>
              <EditableConfigRow
                label="Confidence threshold (approve if below)"
                configKey="approval_confidence_threshold"
                currentValue={
                  config.approval_rules[0]?.confidence_threshold?.toString() ??
                  "0.75"
                }
                saving={configSaving}
                success={configSuccess}
                error={rowErrors["cfg:approval_confidence_threshold"]}
                onSave={handleConfigSave}
                hint="Value between 0 and 1 (e.g. 0.75)"
              />
              {config.approval_rules.map((rule) => (
                <EditableApprovalRuleRow
                  key={rule.agent_name}
                  rule={rule}
                  saving={ruleSaving}
                  success={ruleSuccess}
                  error={rowErrors[`rule:${rule.agent_name}`]}
                  onSave={handleApprovalRuleSave}
                />
              ))}
            </section>
          )}
        </div>
      )}
    </div>
  );
}
