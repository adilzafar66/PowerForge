"""One locked transaction for the complete equipment draft; no inner commits."""

from powerforge_api.exceptions import InvalidTopology
from powerforge_api.schemas.model import EquipmentEditorResponse, EquipmentEditorUpdate
from powerforge_api.services.engineering_model_service import EngineeringModelService
from powerforge_api.services.topology_service import TopologyService
from powerforge_engineering_model import InformationState
from powerforge_persistence.topology import ModelNode


def editor_snapshot(session, project_id, revision_id, equipment_id):
    equipment = EngineeringModelService(session)
    row = equipment.get_equipment(project_id, revision_id, equipment_id)
    return dict(
        equipment=row,
        attributes=equipment.get_equipment_attributes(project_id, revision_id, equipment_id),
        terminals=[
            n
            for n in TopologyService(session).list_nodes(
                project_id, revision_id, lifecycle_status=None
            )
            if n.equipment_id == row.id
        ],
    )


def save_equipment_editor(
    session, project_id, revision_id, equipment_id, draft: EquipmentEditorUpdate
):
    service = EngineeringModelService(session, commit=False)
    topology = TopologyService(session, commit=False)
    with EngineeringModelService(session)._mutation(
        project_id, revision_id, "save_equipment_editor"
    ):
        equipment = service.get_equipment(project_id, revision_id, equipment_id)
        service._assert_active(equipment)
        # Check every terminal belongs to the editor owner before applying any changes.
        for node_id in (
            [t.id for t in draft.update_terminals]
            + draft.remove_terminals
            + draft.restore_terminals
        ):
            node = topology._row(ModelNode, project_id, revision_id, node_id)
            if node.equipment_id != equipment_id:
                raise InvalidTopology("Terminal does not belong to this equipment")
        # Resets may make an incompatible old attribute safely discardable in this same save.
        reset_keys = set()
        existing_keys = {row.attribute_key for row in equipment.attributes}
        for key, edit in draft.attributes.items():
            if key in existing_keys and edit.information_state == InformationState.NOT_POPULATED:
                service.set_attribute(
                    project_id,
                    revision_id,
                    equipment_id,
                    key,
                    edit.information_state,
                    value=edit.value,
                    input_unit=edit.unit,
                )
                reset_keys.add(key)
        if draft.general:
            service.update_equipment(
                project_id,
                revision_id,
                equipment_id,
                **draft.general.model_dump(exclude_unset=True),
            )
        for key, edit in draft.attributes.items():
            if key in reset_keys:
                continue
            service.set_attribute(
                project_id,
                revision_id,
                equipment_id,
                key,
                edit.information_state,
                value=edit.value,
                input_unit=edit.unit,
            )
        for edit in draft.create_terminals:
            topology.create_terminal(project_id, revision_id, equipment_id, **edit.model_dump())
        for edit in draft.update_terminals:
            topology.update_node(
                project_id,
                revision_id,
                edit.id,
                **edit.model_dump(exclude={"id"}, exclude_unset=True),
            )
        for node_id in draft.remove_terminals:
            topology.remove_node(project_id, revision_id, node_id)
        for node_id in draft.restore_terminals:
            topology.restore_node(project_id, revision_id, node_id)
        snapshot = editor_snapshot(session, project_id, revision_id, equipment_id)
        # Serialize under the lock so validation errors also roll back the complete draft.
        result = EquipmentEditorResponse.model_validate(snapshot)
    return result
