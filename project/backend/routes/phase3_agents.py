"""REST routes for Phase 3 vision agents (rendering, mock-up, photo, QC)."""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.schemas import Phase3VisionResultResponse
from backend.services.agent_runs import (
    run_installation_qc_vision,
    run_mockup_vision,
    run_photo_analysis_vision,
    run_rendering_vision,
)
from integrations.vision_verification import VisionAnalysisError, VisionConfigError

router = APIRouter()


async def _read_image(upload: UploadFile, field: str) -> tuple[bytes, str]:
    data = await upload.read()
    if not data:
        raise HTTPException(status_code=400, detail=f"{field} is empty.")
    return data, upload.content_type or "image/png"


async def _optional_image(
    upload: UploadFile | None,
    field: str,
) -> tuple[bytes | None, str | None]:
    if upload is None or not upload.filename:
        return None, None
    data, media_type = await _read_image(upload, field)
    return data, media_type


def _handle_vision_errors(fn):
    try:
        return fn()
    except VisionConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except VisionAnalysisError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/rendering/analyze", response_model=Phase3VisionResultResponse)
async def analyze_rendering(
    site_image: UploadFile = File(..., description="Storefront / site photo"),
    design_brief: str = Form("", description="Design brief for rendering"),
    project_id: str = Form("", description="Optional project identifier"),
    artwork_image: UploadFile | None = File(
        None,
        description="Optional artwork reference image",
    ),
) -> Phase3VisionResultResponse:
    """AI Rendering — assess site photo and produce design alternatives."""
    site_bytes, site_type = await _read_image(site_image, "site_image")
    artwork_bytes, artwork_type = await _optional_image(artwork_image, "artwork_image")

    result = _handle_vision_errors(
        lambda: run_rendering_vision(
            site_image_bytes=site_bytes,
            site_media_type=site_type,
            design_brief=design_brief,
            artwork_image_bytes=artwork_bytes,
            artwork_media_type=artwork_type,
            project_id=project_id,
        )
    )
    return Phase3VisionResultResponse.model_validate(result)


@router.post("/mockup/analyze", response_model=Phase3VisionResultResponse)
async def analyze_mockup(
    site_image: UploadFile = File(..., description="Site / install location photo"),
    artwork_image: UploadFile = File(..., description="Artwork overlay image"),
    brief: str = Form("", description="Mock-up brief"),
    project_id: str = Form("", description="Optional project identifier"),
    client_email: str = Form("", description="Client email for external share gate"),
) -> Phase3VisionResultResponse:
    """AI Mock-up — assess composite readiness before external share."""
    site_bytes, site_type = await _read_image(site_image, "site_image")
    art_bytes, art_type = await _read_image(artwork_image, "artwork_image")

    result = _handle_vision_errors(
        lambda: run_mockup_vision(
            site_image_bytes=site_bytes,
            site_media_type=site_type,
            artwork_image_bytes=art_bytes,
            artwork_media_type=art_type,
            brief=brief,
            project_id=project_id,
            client_email=client_email,
        )
    )
    return Phase3VisionResultResponse.model_validate(result)


@router.post("/photo-analysis/analyze", response_model=Phase3VisionResultResponse)
async def analyze_photo(
    survey_image: UploadFile = File(..., description="Survey / site photo"),
    context: str = Form("", description="Optional project context"),
    project_id: str = Form("", description="Optional project identifier"),
    monday_item_id: str = Form("", description="Optional Monday item for write-back"),
) -> Phase3VisionResultResponse:
    """Photo Analysis — extract branding and installation context from survey photos."""
    survey_bytes, survey_type = await _read_image(survey_image, "survey_image")

    result = _handle_vision_errors(
        lambda: run_photo_analysis_vision(
            survey_image_bytes=survey_bytes,
            survey_media_type=survey_type,
            context=context,
            project_id=project_id,
            monday_item_id=monday_item_id,
        )
    )
    return Phase3VisionResultResponse.model_validate(result)


@router.post("/installation-qc/analyze", response_model=Phase3VisionResultResponse)
async def analyze_installation_qc(
    install_image: UploadFile = File(..., description="Installation photo"),
    reference_image: UploadFile = File(..., description="Approved rendering / reference"),
    spec_notes: str = Form("", description="Optional QC spec notes"),
    project_id: str = Form("", description="Optional project identifier"),
    monday_item_id: str = Form("", description="Optional Monday item for QC status"),
) -> Phase3VisionResultResponse:
    """Installation QC — compare install photo against approved reference."""
    install_bytes, install_type = await _read_image(install_image, "install_image")
    ref_bytes, ref_type = await _read_image(reference_image, "reference_image")

    result = _handle_vision_errors(
        lambda: run_installation_qc_vision(
            install_image_bytes=install_bytes,
            install_media_type=install_type,
            reference_image_bytes=ref_bytes,
            reference_media_type=ref_type,
            spec_notes=spec_notes,
            project_id=project_id,
            monday_item_id=monday_item_id,
        )
    )
    return Phase3VisionResultResponse.model_validate(result)
