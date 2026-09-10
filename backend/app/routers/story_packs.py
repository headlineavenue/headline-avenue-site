from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Story, StoryOutput
from ..schemas import StoryOutputOut, StoryPackGenerate, StoryPackOut

router = APIRouter(prefix="/story-packs", tags=["story-packs"])


@router.post("/generate", response_model=StoryPackOut, status_code=201)
def generate_story_pack(payload: StoryPackGenerate, db: Session = Depends(get_db)) -> StoryPackOut:
    story = db.get(Story, payload.story_id)
    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    outputs: list[StoryOutput] = []
    for output_type in dict.fromkeys(payload.formats):
        output = StoryOutput(
            story_id=story.id,
            output_type=output_type,
            status="ready",
            content_json={
                "title": story.title,
                "angle": story.angle,
                "note": "Prototype output record. Generation service plugs in here.",
            },
        )
        db.add(output)
        outputs.append(output)

    story.status = "pack_ready"
    db.commit()
    for output in outputs:
        db.refresh(output)

    return StoryPackOut(
        story_id=story.id,
        outputs=[StoryOutputOut.model_validate(output) for output in outputs],
    )
