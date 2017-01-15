#########
# Copyright (c) 2013 GigaSpaces Technologies Ltd. All rights reserved
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
#  * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  * See the License for the specific language governing permissions and
#  * limitations under the License.

from flask_restful import fields as flask_fields
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.associationproxy import association_proxy

from manager_rest.utils import classproperty
from manager_rest.rest.responses import Workflow
from manager_rest.deployment_update.constants import ACTION_TYPES, ENTITY_TYPES

from .models_base import db, UTCDateTime
from .relationships import foreign_key, one_to_many_relationship
from .resource_models_base import (TopLevelResource,
                                   DerivedResource,
                                   SQLResourceBase)
from .mixins import (DerivedTenantMixin,
                     TopLevelCreatorMixin,
                     TopLevelMixin)
from .models_states import (DeploymentModificationState,
                            SnapshotState,
                            ExecutionState)


# region Top Level Resources

class Blueprint(TopLevelResource):
    __tablename__ = 'blueprints'

    skipped_fields = dict(
        TopLevelResource.skipped_fields,
        v1=['main_file_name', 'description']
    )

    created_at = db.Column(UTCDateTime, nullable=False, index=True)
    main_file_name = db.Column(db.Text, nullable=False)
    plan = db.Column(db.PickleType, nullable=False)
    updated_at = db.Column(UTCDateTime)
    description = db.Column(db.Text)


class Snapshot(TopLevelResource):
    __tablename__ = 'snapshots'

    created_at = db.Column(UTCDateTime, nullable=False, index=True)
    status = db.Column(db.Enum(*SnapshotState.STATES, name='snapshot_status'))
    error = db.Column(db.Text)


class Plugin(TopLevelResource):
    __tablename__ = 'plugins'

    archive_name = db.Column(db.Text, nullable=False, index=True)
    distribution = db.Column(db.Text)
    distribution_release = db.Column(db.Text)
    distribution_version = db.Column(db.Text)
    excluded_wheels = db.Column(db.PickleType)
    package_name = db.Column(db.Text, nullable=False, index=True)
    package_source = db.Column(db.Text)
    package_version = db.Column(db.Text)
    supported_platform = db.Column(db.PickleType)
    supported_py_versions = db.Column(db.PickleType)
    uploaded_at = db.Column(UTCDateTime, nullable=False, index=True)
    wheels = db.Column(db.PickleType, nullable=False)

# endregion


# region Derived Resources

class Deployment(TopLevelCreatorMixin, DerivedTenantMixin, SQLResourceBase):
    __tablename__ = 'deployments'

    skipped_fields = dict(
        TopLevelResource.skipped_fields,
        v1=['scaling_groups'],
        v2=['scaling_groups']
    )

    created_at = db.Column(UTCDateTime, nullable=False, index=True)
    description = db.Column(db.Text)
    inputs = db.Column(db.PickleType)
    groups = db.Column(db.PickleType)
    permalink = db.Column(db.Text)
    policy_triggers = db.Column(db.PickleType)
    policy_types = db.Column(db.PickleType)
    outputs = db.Column(db.PickleType(comparator=lambda *a: False))
    scaling_groups = db.Column(db.PickleType)
    updated_at = db.Column(UTCDateTime)
    workflows = db.Column(db.PickleType(comparator=lambda *a: False))

    _blueprint_fk = foreign_key(Blueprint._storage_id)

    @declared_attr
    def blueprint(cls):
        return one_to_many_relationship(cls, Blueprint, cls._blueprint_fk)

    @hybrid_property
    def parent(self):
        return self.blueprint

    @parent.expression
    def parent(cls):
        return Blueprint

    blueprint_id = association_proxy('blueprint', 'id')
    _tenant_id = association_proxy('blueprint', '_tenant_id')

    @classproperty
    def response_fields(cls):
        fields = super(Deployment, cls).response_fields
        fields['workflows'] = flask_fields.List(
            flask_fields.Nested(Workflow.resource_fields)
        )
        return fields

    def to_response(self):
        dep_dict = super(Deployment, self).to_response()
        dep_dict['workflows'] = self._list_workflows(self.workflows)
        return dep_dict

    @staticmethod
    def _list_workflows(deployment_workflows):
        if deployment_workflows is None:
            return None

        return [Workflow(name=wf_name,
                         created_at=None,
                         parameters=wf.get('parameters', dict()))
                for wf_name, wf in deployment_workflows.iteritems()]


class Execution(TopLevelMixin, SQLResourceBase):
    __tablename__ = 'executions'

    created_at = db.Column(UTCDateTime, nullable=False, index=True)
    error = db.Column(db.Text)
    is_system_workflow = db.Column(db.Boolean, nullable=False)
    parameters = db.Column(db.PickleType)
    status = db.Column(
        db.Enum(*ExecutionState.STATES, name='execution_status')
    )
    workflow_id = db.Column(db.Text, nullable=False)

    _deployment_fk = foreign_key(Deployment._storage_id, nullable=True)

    @declared_attr
    def deployment(cls):
        return one_to_many_relationship(cls, Deployment, cls._deployment_fk)

    deployment_id = association_proxy('deployment', 'id')
    blueprint_id = association_proxy('deployment', 'blueprint_id')

    @hybrid_property
    def parent(self):
        return self.deployment

    @parent.expression
    def parent(cls):
        return Deployment

    def __repr__(self):
        id_name, id_value = self._get_identifier()
        return '<{0} {1}=`{2}`; tenant=`{3}` (status={4})>'.format(
            self.__class__.__name__,
            id_name,
            id_value,
            self.tenant_name,
            self.status
        )


class Event(DerivedResource):

    """Execution events."""

    __tablename__ = 'events'

    timestamp = db.Column(UTCDateTime, nullable=False, index=True)
    message = db.Column(db.Text)
    message_code = db.Column(db.Text)
    event_type = db.Column(db.Text)

    _execution_fk = foreign_key(Execution._storage_id, nullable=False)

    @declared_attr
    def execution(cls):
        return one_to_many_relationship(cls, Execution, cls._execution_fk)

    execution_id = association_proxy('execution', 'id')

    @hybrid_property
    def parent(self):
        return self.execution

    @parent.expression
    def parent(cls):
        return Execution


class Log(DerivedResource):

    """Execution logs."""

    __tablename__ = 'logs'

    timestamp = db.Column(UTCDateTime, nullable=False, index=True)
    message = db.Column(db.Text)
    message_code = db.Column(db.Text)

    logger = db.Column(db.Text)
    level = db.Column(db.Text)

    _execution_fk = foreign_key(Execution._storage_id, nullable=False)

    @declared_attr
    def execution(cls):
        return one_to_many_relationship(cls, Execution, cls._execution_fk)

    execution_id = association_proxy('execution', 'id')

    @hybrid_property
    def parent(self):
        return self.execution

    @parent.expression
    def parent(cls):
        return Execution


class DeploymentUpdate(DerivedResource):
    __tablename__ = 'deployment_updates'

    created_at = db.Column(UTCDateTime, nullable=False, index=True)
    deployment_plan = db.Column(db.PickleType)
    deployment_update_node_instances = db.Column(db.PickleType)
    deployment_update_deployment = db.Column(db.PickleType)
    deployment_update_nodes = db.Column(db.PickleType)
    modified_entity_ids = db.Column(db.PickleType)
    state = db.Column(db.Text)

    _execution_fk = foreign_key(Execution._storage_id, nullable=True)
    _deployment_fk = foreign_key(Deployment._storage_id)

    @declared_attr
    def execution(cls):
        return one_to_many_relationship(cls, Execution, cls._execution_fk)

    @declared_attr
    def deployment(cls):
        return one_to_many_relationship(cls, Deployment, cls._deployment_fk)

    @hybrid_property
    def parent(self):
        return self.deployment

    @parent.expression
    def parent(cls):
        return Deployment

    deployment_id = association_proxy('deployment', 'id')
    execution_id = association_proxy('execution', 'id')
    _tenant_id = association_proxy('deployment', '_tenant_id')

    @classproperty
    def response_fields(cls):
        fields = super(DeploymentUpdate, cls).response_fields
        fields['steps'] = flask_fields.List(
            flask_fields.Nested(DeploymentUpdateStep.response_fields)
        )
        return fields

    def to_response(self):
        dep_update_dict = super(DeploymentUpdate, self).to_response()
        # Taking care of the fact the DeploymentSteps are objects
        dep_update_dict['steps'] = [step.to_dict() for step in self.steps]
        return dep_update_dict


class DeploymentUpdateStep(DerivedResource):
    __tablename__ = 'deployment_update_steps'

    action = db.Column(db.Enum(*ACTION_TYPES, name='action_type'))
    entity_id = db.Column(db.Text, nullable=False)
    entity_type = db.Column(db.Enum(*ENTITY_TYPES, name='entity_type'))

    _deployment_update_fk = foreign_key(DeploymentUpdate._storage_id)

    @declared_attr
    def deployment_update(cls):
        return one_to_many_relationship(cls,
                                        DeploymentUpdate,
                                        cls._deployment_update_fk,
                                        backreference='steps')

    @hybrid_property
    def parent(self):
        return self.deployment_update

    @parent.expression
    def parent(cls):
        return DeploymentUpdate

    deployment_update_id = association_proxy('deployment_update', 'id')
    _tenant_id = association_proxy('deployment_update', '_tenant_id')


class DeploymentModification(DerivedResource):
    __tablename__ = 'deployment_modifications'

    context = db.Column(db.PickleType)
    created_at = db.Column(UTCDateTime, nullable=False, index=True)
    ended_at = db.Column(UTCDateTime, index=True)
    modified_nodes = db.Column(db.PickleType)
    node_instances = db.Column(db.PickleType)
    status = db.Column(db.Enum(
        *DeploymentModificationState.STATES,
        name='deployment_modification_status'
    ))

    _deployment_fk = foreign_key(Deployment._storage_id)

    @declared_attr
    def deployment(cls):
        return one_to_many_relationship(cls,
                                        Deployment,
                                        cls._deployment_fk,
                                        backreference='modifications')

    @hybrid_property
    def parent(self):
        return self.deployment

    @parent.expression
    def parent(cls):
        return Deployment

    deployment_id = association_proxy('deployment', 'id')
    _tenant_id = association_proxy('deployment', '_tenant_id')


class Node(DerivedResource):
    __tablename__ = 'nodes'

    is_id_unique = False
    skipped_fields = dict(
        TopLevelResource.skipped_fields,
        v1=['max_number_of_instances', 'min_number_of_instances'],
        v2=['max_number_of_instances', 'min_number_of_instances']
    )

    deploy_number_of_instances = db.Column(db.Integer, nullable=False)
    # TODO: This probably should be a foreign key, but there's no guarantee
    # in the code, currently, that the host will be created beforehand
    host_id = db.Column(db.Text)
    max_number_of_instances = db.Column(db.Integer, nullable=False)
    min_number_of_instances = db.Column(db.Integer, nullable=False)
    number_of_instances = db.Column(db.Integer, nullable=False)
    planned_number_of_instances = db.Column(db.Integer, nullable=False)
    plugins = db.Column(db.PickleType)
    plugins_to_install = db.Column(db.PickleType)
    properties = db.Column(db.PickleType)
    relationships = db.Column(db.PickleType)
    operations = db.Column(db.PickleType)
    type = db.Column(db.Text, nullable=False, index=True)
    type_hierarchy = db.Column(db.PickleType)

    _deployment_fk = foreign_key(Deployment._storage_id)

    @declared_attr
    def deployment(cls):
        return one_to_many_relationship(cls, Deployment, cls._deployment_fk)

    @hybrid_property
    def parent(self):
        return self.deployment

    @parent.expression
    def parent(cls):
        return Deployment

    deployment_id = association_proxy('deployment', 'id')
    blueprint_id = association_proxy('deployment', 'blueprint_id')
    _tenant_id = association_proxy('deployment', '_tenant_id')


class NodeInstance(DerivedResource):
    __tablename__ = 'node_instances'

    skipped_fields = dict(
        TopLevelResource.skipped_fields,
        v1=['scaling_groups'],
        v2=['scaling_groups']
    )

    # TODO: This probably should be a foreign key, but there's no guarantee
    # in the code, currently, that the host will be created beforehand
    host_id = db.Column(db.Text)
    relationships = db.Column(db.PickleType)
    runtime_properties = db.Column(db.PickleType)
    scaling_groups = db.Column(db.PickleType)
    state = db.Column(db.Text, nullable=False)
    version = db.Column(db.Integer, default=1)

    _node_fk = foreign_key(Node._storage_id)

    @declared_attr
    def node(cls):
        return one_to_many_relationship(cls, Node, cls._node_fk)

    @hybrid_property
    def parent(self):
        return self.node

    @parent.expression
    def parent(cls):
        return Node

    node_id = association_proxy('node', 'id')
    deployment_id = association_proxy('node', 'deployment_id')
    _tenant_id = association_proxy('node', '_tenant_id')

# endregion
