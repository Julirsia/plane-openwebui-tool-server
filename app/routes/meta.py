from fastapi import APIRouter, Depends

from app.deps import get_app_settings, get_plane_client, get_template_registry, get_transition_policy
from app.models import ContextResponse, MemberItem, MetaItem, TemplateInfo

router = APIRouter(prefix="/meta", tags=["meta"])


@router.get("/context", response_model=ContextResponse)
async def get_context(
    plane_client=Depends(get_plane_client),
    registry=Depends(get_template_registry),
    transition_policy=Depends(get_transition_policy),
    settings=Depends(get_app_settings),
) -> ContextResponse:
    project = await plane_client.get_project()
    states = await plane_client.list_states()
    labels = await plane_client.list_labels()
    members = await plane_client.list_project_members()
    templates = [
        TemplateInfo(
            id=template["id"],
            display_name=template["display_name"],
            editable_sections=list(template.get("editable_sections", [])),
        )
        for template in registry.list_templates()
    ]
    return ContextResponse(
        project=project,
        states=[MetaItem(id=item["id"], name=item["name"]) for item in states],
        labels=[MetaItem(id=item["id"], name=item["name"]) for item in labels],
        members=[MemberItem(id=item["id"], display_name=item.get("display_name") or item.get("member", {}).get("display_name", "")) for item in members],
        templates=templates,
        transition_policy=transition_policy,
        editable_sections_by_template=registry.editable_sections_by_template(),
        limits={
            "search_limit_max": 50,
            "section_update_max_per_request": 6,
            "default_comment_limit": settings.default_comment_limit,
            "default_activity_limit": settings.default_activity_limit,
        },
    )
