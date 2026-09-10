from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Story, StoryOutput
from ..schemas import StoryOutputOut, StoryPackGenerate, StoryPackOut

router = APIRouter(prefix="/story-packs", tags=["story-packs"])


def _latest_editorial_selection(db: Session, story_id: str) -> StoryOutput | None:
    return (
        db.query(StoryOutput)
        .filter(
            StoryOutput.story_id == story_id,
            StoryOutput.output_type == "editorial_selection",
        )
        .order_by(StoryOutput.created_at.desc(), StoryOutput.id.desc())
        .first()
    )


@router.post("/generate", response_model=StoryPackOut, status_code=201)
def generate_story_pack(payload: StoryPackGenerate, db: Session = Depends(get_db)) -> StoryPackOut:
    story = db.get(Story, payload.story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    editorial = _latest_editorial_selection(db, story.id)
    publish_ready = bool(editorial and editorial.status in {"ready", "approved"})
    pack_status = "ready" if publish_ready else "needs_review"

    gate_note = None
    if not editorial:
        gate_note = "Choose and save an editorial headline before publishing."
    elif editorial.status == "needs_review":
        gate_note = "Latest editorial headline requires SourceGuard review or editor approval before publishing."

    outputs: list[StoryOutput] = []
    for output_type in dict.fromkeys(payload.formats):
        output = StoryOutput(
            story_id=story.id,
            output_type=output_type,
            status=pack_status,
            content_json={
                "title": story.title,
                "angle": story.angle,
                "note": "Prototype output record. Generation service plugs in here.",
                "editorial_gate": {
                    "publish_ready": publish_ready,
                    "selection_id": editorial.id if editorial else None,
                    "selection_status": editorial.status if editorial else "missing",
                    "review_note": gate_note,
                },
            },
        )
        db.add(output)
        outputs.append(output)

    story.status = "pack_ready" if publish_ready else "needs_review"
    db.commit()
    for output in outputs:
        db.refresh(output)

    return StoryPackOut(
        story_id=story.id,
        outputs=[StoryOutputOut.model_validate(output) for output in outputs],
    )
