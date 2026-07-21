"""REST routes for the Artwork Verification Agent."""

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.schemas import (
    ArtworkCardResponse,
    ArtworkNumericVerifyRequest,
    ArtworkVisionResultResponse,
)
from backend.services.agent_runs import run_artwork_numeric, run_artwork_vision
from integrations.vision_verification import VisionAnalysisError, VisionConfigError

router = APIRouter()


@router.post("/verify-numeric", response_model=ArtworkCardResponse)
def verify_artwork_numeric(
    body: ArtworkNumericVerifyRequest,
) -> ArtworkCardResponse:
    """Rule-based dimension check on user-entered artwork vs spec sizes."""
    result = run_artwork_numeric(
        project_id=body.project_id,
        artwork_width_inches=body.artwork_width_inches,
        artwork_height_inches=body.artwork_height_inches,
        spec_width_inches=body.spec_width_inches,
        spec_height_inches=body.spec_height_inches,
        submitted_by=body.submitted_by,
    )
    return ArtworkCardResponse.model_validate(result)


@router.post("/verify-vision", response_model=ArtworkVisionResultResponse)
async def verify_artwork_vision(
    artwork_image: UploadFile = File(..., description="Artwork image to verify"),
    spec_description: str = Form(
        "",
        description="Text description of expected dimensions / design",
    ),
    project_id: str = Form("", description="Optional project identifier"),
    spec_image: UploadFile | None = File(
        None,
        description="Optional reference / spec image",
    ),
) -> ArtworkVisionResultResponse:
    """Vision-based artwork check via Claude (multipart upload).

    Accepts an artwork image plus a text spec and optional reference image.
    Results are logged through the Supervisor audit flow. MISMATCH and
    UNCERTAIN require human review.
    """
    artwork_bytes = await artwork_image.read()
    if not artwork_bytes:
        raise HTTPException(status_code=400, detail="artwork_image is empty.")

    artwork_media_type = artwork_image.content_type or "image/png"

    spec_bytes: bytes | None = None
    spec_media_type: str | None = None
    if spec_image is not None and spec_image.filename:
        spec_bytes = await spec_image.read()
        if not spec_bytes:
            raise HTTPException(status_code=400, detail="spec_image is empty.")
        spec_media_type = spec_image.content_type or "image/png"

    try:
        result = run_artwork_vision(
            artwork_image_bytes=artwork_bytes,
            artwork_media_type=artwork_media_type,
            spec_description=spec_description,
            spec_image_bytes=spec_bytes,
            spec_media_type=spec_media_type,
            project_id=project_id,
        )
    except VisionConfigError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except VisionAnalysisError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return ArtworkVisionResultResponse.model_validate(result)
