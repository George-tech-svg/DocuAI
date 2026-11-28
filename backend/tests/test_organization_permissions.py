from types import SimpleNamespace

from app.services.permissions import ALL_ACTIONS, ROLE_ACTIONS, can, role_allows
from app.models.entities import Organization, KnowledgeBase, Conversation


def test_every_role_and_action_uses_the_documented_permission_matrix():
    for role in ('owner', 'admin', 'member', 'viewer', 'unknown'):
        for action in ALL_ACTIONS:
            expected = action in ROLE_ACTIONS.get(role, set())
            assert role_allows(role, action) is expected, (role, action)
    assert not role_allows('owner', 'arbitrary_action')


class FakeDb:
    def __init__(self, role): self.role = role; self.organization = Organization(id='org-1')
    def get(self, model, key): return self.organization if model is Organization else None
    def scalar(self, statement): return self.role


def test_organization_folder_permission_comes_from_membership_role():
    user = SimpleNamespace(id='user-1')
    folder = KnowledgeBase(id='folder-1', user_id='creator-1', organization_id='org-1')
    assert can(user, 'read', folder, FakeDb('viewer'))
    assert can(user, 'chat', folder, FakeDb('viewer'))
    assert not can(user, 'upload', folder, FakeDb('viewer'))
    assert can(user, 'upload', folder, FakeDb('member'))


def test_organization_resource_enforces_every_role_action_combination():
    user = SimpleNamespace(id='user-1')
    organization = Organization(id='org-1')
    for role in ('owner', 'admin', 'member', 'viewer', 'unknown'):
        db = FakeDb(role)
        for action in ALL_ACTIONS:
            assert can(user, action, organization, db) is role_allows(role, action), (role, action)


def test_existing_personal_folder_ownership_is_preserved():
    owner = SimpleNamespace(id='legacy-user')
    other = SimpleNamespace(id='other-user')
    folder = KnowledgeBase(id='legacy-folder', user_id='legacy-user', organization_id=None)
    assert can(owner, 'read', folder, FakeDb(None))
    assert can(owner, 'upload', folder, FakeDb(None))
    assert not can(other, 'read', folder, FakeDb(None))


def test_legacy_personal_documents_and_conversations_stay_private_to_owner():
    owner = SimpleNamespace(id='legacy-user')
    other = SimpleNamespace(id='other-user')
    folder = KnowledgeBase(id='legacy-folder', user_id='legacy-user', organization_id=None)
    private_chat = Conversation(id='chat-1', user_id='legacy-user', knowledge_base_id='legacy-folder', visibility='private')
    db = FakeDb(None)
    db.get = lambda model, key: folder if model is KnowledgeBase else None
    assert can(owner, 'chat', private_chat, db)
    assert not can(other, 'read', private_chat, db)
