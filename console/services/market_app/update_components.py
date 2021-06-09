# -*- coding: utf8 -*-

from console.services.market_app.original_app import OriginalApp
from console.services.market_app.property_changes import PropertyChanges
from console.exception.main import AbortRequest


class UpdateComponents(object):
    """
    components that need to be updated.
    """

    def __init__(self, original_app: OriginalApp, app_model_key, app_template, version, components_keys):
        """
        components_keys: component keys that the user select.
        """
        self.original_app = original_app
        self.app_model_key = app_model_key
        self.app_template = app_template
        self.version = version
        self.components_keys = components_keys
        self.components = self._create_update_components()

    def _create_update_components(self):
        """
        component templates + existing components => update components
        """
        # filter by self.components_keys
        components = []
        for cpt in self.original_app.components():
            if self.components_keys and cpt.component.service_key not in self.components_keys:
                continue
            components.append(cpt)

        pc = PropertyChanges(components, self.app_template)
        if not pc.need_change():
            raise AbortRequest("no changes", "应用无变化, 无需升级")

        cpt_changes = {change["component_id"]: change for change in pc.changes}
        for cpt in components:
            cpt.set_changes(cpt_changes[cpt.component.component_id], self.original_app.governance_mode)
            cpt.component_source.group_key = self.app_model_key
            cpt.component_source.version = self.version

        return components
