import "next-auth";
import "next-auth/jwt";
import type { DefaultSession } from "next-auth";

type OperatorRole = "operator" | "reviewer" | "admin";

declare module "next-auth" {
  interface User {
    role?: OperatorRole;
  }

  interface Session {
    user: {
      role: OperatorRole;
    } & DefaultSession["user"];
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    role?: OperatorRole;
  }
}
