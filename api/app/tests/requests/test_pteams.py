import json
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models, schemas
from app.constants import (
    DEFAULT_ALERT_THREAT_IMPACT,
    MEMBER_UUID,
    NOT_MEMBER_UUID,
    ZERO_FILLED_UUID,
)
from app.main import app
from app.tests.common import threat_utils, ticket_utils
from app.tests.medium.constants import (
    ACTION1,
    ACTION2,
    ATEAM1,
    PTEAM1,
    PTEAM2,
    TAG1,
    TAG2,
    TOPIC1,
    TOPIC2,
    USER1,
    USER2,
    USER3,
)
from app.tests.medium.exceptions import HTTPError
from app.tests.medium.utils import (
    accept_pteam_invitation,
    accept_watching_request,
    assert_200,
    assert_204,
    calc_file_sha256,
    compare_references,
    compare_tags,
    create_ateam,
    create_pteam,
    create_service_topicstatus,
    create_tag,
    create_topic,
    create_user,
    create_watching_request,
    file_upload_headers,
    get_pteam_services,
    get_pteam_tags,
    headers,
    invite_to_pteam,
    schema_to_dict,
    upload_pteam_tags,
)

client = TestClient(app)


def test_get_pteams():
    create_user(USER1)

    response = client.get("/pteams", headers=headers(USER1))
    assert response.status_code == 200
    assert response.json() == []

    pteam1 = create_pteam(USER1, PTEAM1)

    response = client.get("/pteams", headers=headers(USER1))
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["pteam_id"] == str(pteam1.pteam_id)
    assert data[0]["pteam_name"] == PTEAM1["pteam_name"]
    assert data[0]["contact_info"] == PTEAM1["contact_info"]


def test_get_pteams__without_auth():
    response = client.get("/pteams")  # no headers
    assert response.status_code == 401
    assert response.reason_phrase == "Unauthorized"


def test_get_pteams__by_member():
    create_user(USER1)
    create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)
    accept_pteam_invitation(USER2, invitation.invitation_id)

    response = client.get("/pteams", headers=headers(USER2))
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["pteam_id"] == str(pteam1.pteam_id)
    assert data[0]["pteam_name"] == PTEAM1["pteam_name"]
    assert data[0]["contact_info"] == PTEAM1["contact_info"]


def test_get_pteams__by_not_member():
    create_user(USER1)
    create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)

    response = client.get("/pteams", headers=headers(USER2))  # not a member
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["pteam_id"] == str(pteam1.pteam_id)
    assert data[0]["pteam_name"] == PTEAM1["pteam_name"]
    assert data[0]["contact_info"] == PTEAM1["contact_info"]
    assert "tag_name" not in data[0].keys()


def test_get_pteam():
    create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)

    response = client.get(f"/pteams/{pteam1.pteam_id}", headers=headers(USER1))
    assert response.status_code == 200
    data = response.json()
    assert data["pteam_id"] == str(pteam1.pteam_id)
    assert data["contact_info"] == PTEAM1["contact_info"]
    assert data["pteam_name"] == PTEAM1["pteam_name"]
    assert data["alert_slack"]["enable"] == PTEAM1["alert_slack"]["enable"]
    assert data["alert_slack"]["webhook_url"] == PTEAM1["alert_slack"]["webhook_url"]
    assert data["alert_mail"]["enable"] == PTEAM1["alert_mail"]["enable"]
    assert data["alert_mail"]["address"] == PTEAM1["alert_mail"]["address"]


def test_get_pteam__without_auth():
    create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)

    response = client.get(f"/pteams/{pteam1.pteam_id}")  # no headers
    assert response.status_code == 401
    assert response.reason_phrase == "Unauthorized"


def test_get_pteam__by_member():
    create_user(USER1)
    create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)
    accept_pteam_invitation(USER2, invitation.invitation_id)

    response = client.get(f"/pteams/{pteam1.pteam_id}", headers=headers(USER2))
    assert response.status_code == 200
    data = response.json()
    assert data["pteam_id"] == str(pteam1.pteam_id)
    assert data["contact_info"] == PTEAM1["contact_info"]
    assert data["pteam_name"] == PTEAM1["pteam_name"]
    assert data["alert_slack"]["enable"] == PTEAM1["alert_slack"]["enable"]
    assert data["alert_slack"]["webhook_url"] == PTEAM1["alert_slack"]["webhook_url"]


def test_get_pteam__by_not_member():
    create_user(USER1)
    create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)

    response = client.get(f"/pteams/{pteam1.pteam_id}", headers=headers(USER2))  # not a member
    assert response.status_code == 403
    assert response.reason_phrase == "Forbidden"


def test_create_pteam():
    create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)
    assert pteam1.pteam_name == PTEAM1["pteam_name"]
    assert pteam1.contact_info == PTEAM1["contact_info"]
    assert pteam1.alert_slack.webhook_url == PTEAM1["alert_slack"]["webhook_url"]
    assert pteam1.alert_threat_impact == PTEAM1["alert_threat_impact"]
    assert pteam1.pteam_id != ZERO_FILLED_UUID

    response = client.get("/users/me", headers=headers(USER1))
    assert response.status_code == 200
    user_me = response.json()
    assert {UUID(pteam["pteam_id"]) for pteam in user_me["pteams"]} == {pteam1.pteam_id}

    pteam2 = create_pteam(USER1, PTEAM2)
    assert pteam2.pteam_name == PTEAM2["pteam_name"]
    assert pteam2.contact_info == PTEAM2["contact_info"]
    assert pteam2.alert_slack.webhook_url == PTEAM2["alert_slack"]["webhook_url"]
    assert pteam2.alert_threat_impact == PTEAM2["alert_threat_impact"]
    assert pteam2.pteam_id != ZERO_FILLED_UUID

    response = client.get("/users/me", headers=headers(USER1))
    assert response.status_code == 200
    user_me = response.json()
    assert {UUID(pteam["pteam_id"]) for pteam in user_me["pteams"]} == {
        pteam1.pteam_id,
        pteam2.pteam_id,
    }


def test_create_pteam__by_default():
    create_user(USER1)
    _pteam = PTEAM1.copy()
    del _pteam["contact_info"]
    del _pteam["alert_slack"]
    del _pteam["alert_threat_impact"]
    del _pteam["alert_mail"]
    pteam1 = create_pteam(USER1, _pteam)
    assert pteam1.contact_info == ""
    assert pteam1.alert_slack.enable is True
    assert pteam1.alert_slack.webhook_url == ""
    assert pteam1.alert_threat_impact == DEFAULT_ALERT_THREAT_IMPACT
    assert pteam1.alert_mail.enable is True
    assert pteam1.alert_mail.address == ""


def test_create_pteam__without_auth():
    create_user(USER1)
    request = {**PTEAM1}
    response = client.post("/pteams", json=request)  # no headers
    assert response.status_code == 401
    assert response.reason_phrase == "Unauthorized"


def test_create_pteam__duplicate():
    create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)
    pteam2 = create_pteam(USER1, PTEAM1)
    assert pteam1.pteam_id != pteam2.pteam_id
    del pteam1.pteam_id, pteam2.pteam_id
    assert pteam1 == pteam2


def test_update_pteam():
    create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)

    request = schemas.PTeamUpdateRequest(**PTEAM2).model_dump()
    response = client.put(f"/pteams/{pteam1.pteam_id}", headers=headers(USER1), json=request)
    assert response.status_code == 200
    data = response.json()
    assert data["pteam_name"] == PTEAM2["pteam_name"]
    assert data["contact_info"] == PTEAM2["contact_info"]
    assert data["alert_slack"]["enable"] == PTEAM2["alert_slack"]["enable"]
    assert data["alert_slack"]["webhook_url"] == PTEAM2["alert_slack"]["webhook_url"]
    assert data["alert_threat_impact"] == PTEAM2["alert_threat_impact"]
    assert data["alert_mail"]["enable"] == PTEAM2["alert_mail"]["enable"]
    assert data["alert_mail"]["address"] == PTEAM2["alert_mail"]["address"]


def test_update_pteam__by_admin():
    create_user(USER1)
    create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id, ["admin"])
    accept_pteam_invitation(USER2, invitation.invitation_id)

    request = schemas.PTeamUpdateRequest(**PTEAM2).model_dump()
    data = assert_200(
        client.put(f"/pteams/{pteam1.pteam_id}", headers=headers(USER2), json=request)
    )
    assert data["pteam_name"] == PTEAM2["pteam_name"]
    assert data["contact_info"] == PTEAM2["contact_info"]
    assert data["alert_slack"]["enable"] == PTEAM2["alert_slack"]["enable"]
    assert data["alert_slack"]["webhook_url"] == PTEAM2["alert_slack"]["webhook_url"]
    assert data["alert_threat_impact"] == PTEAM2["alert_threat_impact"]
    assert data["alert_mail"]["enable"] == PTEAM2["alert_mail"]["enable"]
    assert data["alert_mail"]["address"] == PTEAM2["alert_mail"]["address"]


def test_update_pteam__by_not_admin():
    create_user(USER1)
    create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)
    accept_pteam_invitation(USER2, invitation.invitation_id)

    request = schemas.PTeamUpdateRequest(**PTEAM2).model_dump()
    response = client.put(f"/pteams/{pteam1.pteam_id}", headers=headers(USER2), json=request)
    assert response.status_code == 403
    assert response.reason_phrase == "Forbidden"


def test_update_pteam_empty_data():
    create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)

    empty_data = {
        "pteam_name": "",
        "contact_info": "",
        "alert_slack": {"enable": False, "webhook_url": ""},
    }

    request = schemas.PTeamUpdateRequest(**{**empty_data}).model_dump()
    response = client.put(f"/pteams/{pteam1.pteam_id}", headers=headers(USER1), json=request)
    assert response.status_code == 200
    data = response.json()
    assert data["pteam_name"] == ""
    assert data["contact_info"] == ""
    assert data["alert_slack"]["webhook_url"] == ""
    assert data["alert_threat_impact"] == 3


def test_get_pteam_services():
    create_user(USER1)
    create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)
    pteam2 = create_pteam(USER1, PTEAM2)
    create_tag(USER1, TAG1)

    # no services at created pteam
    services1 = get_pteam_services(USER1, pteam1.pteam_id)
    services2 = get_pteam_services(USER1, pteam2.pteam_id)
    assert services1 == services2 == []

    refs0 = {TAG1: [("fake target", "fake version")]}

    # add service x to pteam1
    service_x = "service_x"
    upload_pteam_tags(USER1, pteam1.pteam_id, service_x, refs0)

    services1a = get_pteam_services(USER1, pteam1.pteam_id)
    services2a = get_pteam_services(USER1, pteam2.pteam_id)
    assert services1a[0].service_name == service_x
    assert services2a == []

    # add grserviceoup y to pteam2
    service_y = "service_y"
    upload_pteam_tags(USER1, pteam2.pteam_id, service_y, refs0)

    services1b = get_pteam_services(USER1, pteam1.pteam_id)
    services2b = get_pteam_services(USER1, pteam2.pteam_id)
    assert services1b[0].service_name == service_x
    assert services2b[0].service_name == service_y

    # add service y to pteam1
    upload_pteam_tags(USER1, pteam1.pteam_id, service_y, refs0)

    services1c = get_pteam_services(USER1, pteam1.pteam_id)
    services2c = get_pteam_services(USER1, pteam2.pteam_id)
    print(services1c)
    assert services1c[0].service_name == service_x or service_y
    assert services1c[1].service_name == service_x or service_y
    assert services2c[0].service_name == service_y

    # only members get services
    with pytest.raises(HTTPError, match=r"403: Forbidden: Not a pteam member"):
        get_pteam_services(USER2, pteam1.pteam_id)


def test_get_pteam_tags():
    create_user(USER1)
    create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)
    tag1 = create_tag(USER1, TAG1)
    tag2 = create_tag(USER1, TAG2)

    # no tags at created pteam
    etags0 = get_pteam_tags(USER1, pteam1.pteam_id)
    assert etags0 == []

    # add tag1 to pteam1
    service_x = "service_x"
    refs1 = {tag1.tag_name: [("fake target", "fake version")]}
    expected_ref1 = [
        {"service": service_x, "target": "fake target", "version": "fake version"},
    ]
    etags1a = upload_pteam_tags(USER1, pteam1.pteam_id, service_x, refs1)

    assert len(etags1a) == 1
    assert compare_tags(etags1a, [tag1])
    assert compare_references(etags1a[0].references, expected_ref1)

    etags1b = get_pteam_tags(USER1, pteam1.pteam_id)
    assert len(etags1b) == 1
    assert compare_tags(etags1b, [tag1])
    assert compare_references(etags1b[0].references, expected_ref1)

    # add tag2 to pteam1
    service_y = "service_y"
    refs2 = {tag2.tag_name: [("fake target 2", "fake version 2")]}
    expected_ref2 = [
        {"service": service_y, "target": "fake target 2", "version": "fake version 2"},
    ]
    etags2a = upload_pteam_tags(USER1, pteam1.pteam_id, service_y, refs2)

    assert len(etags2a) == 2
    assert compare_tags(etags2a, sorted([tag1, tag2], key=lambda x: x.tag_name))
    if compare_tags([etags2a[0]], [tag1]):
        assert compare_references(etags2a[0].references, expected_ref1)
        assert compare_references(etags2a[1].references, expected_ref2)
    else:
        assert compare_references(etags2a[1].references, expected_ref1)
        assert compare_references(etags2a[0].references, expected_ref2)

    # only members get tags
    with pytest.raises(HTTPError, match=r"403: Forbidden: Not a pteam member"):
        get_pteam_tags(USER2, pteam1.pteam_id)


def test_get_pteam_tags__by_not_member():
    create_user(USER1)
    create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)

    response = client.get(f"/pteams/{pteam1.pteam_id}/tags", headers=headers(USER2))
    assert response.status_code == 403
    assert response.reason_phrase == "Forbidden"


def test_update_pteam_auth(testdb):
    # access to testdb directly to check auth modified by side effects.

    user1 = create_user(USER1)
    user2 = create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)

    # initial values
    row_user1 = (
        testdb.query(models.PTeamAuthority)
        .filter(
            models.PTeamAuthority.pteam_id == str(pteam1.pteam_id),
            models.PTeamAuthority.user_id == str(user1.user_id),
        )
        .one()
    )
    assert row_user1.authority == models.PTeamAuthIntFlag.PTEAM_MASTER  # pteam master
    row_member = (
        testdb.query(models.PTeamAuthority)
        .filter(
            models.PTeamAuthority.pteam_id == str(pteam1.pteam_id),
            models.PTeamAuthority.user_id == str(MEMBER_UUID),
        )
        .one_or_none()
    )
    if row_member:
        assert row_member.authority == models.PTeamAuthIntFlag.PTEAM_MEMBER  # pteam member
    row_not_member = (
        testdb.query(models.PTeamAuthority)
        .filter(
            models.PTeamAuthority.pteam_id == str(pteam1.pteam_id),
            models.PTeamAuthority.user_id == str(NOT_MEMBER_UUID),
        )
        .one_or_none()
    )
    if row_not_member:
        assert row_not_member.authority == models.PTeamAuthIntFlag.FREE_TEMPLATE  # not member

    # on invitation
    request_auth = list(map(models.PTeamAuthEnum, ["topic_status", "invite"]))
    invitation = invite_to_pteam(USER1, pteam1.pteam_id, request_auth)  # invite with auth
    accept_pteam_invitation(USER2, invitation.invitation_id)
    row_user2 = (
        testdb.query(models.PTeamAuthority)
        .filter(
            models.PTeamAuthority.pteam_id == str(pteam1.pteam_id),
            models.PTeamAuthority.user_id == str(user2.user_id),
        )
        .one()
    )
    assert row_user2.authority == models.PTeamAuthIntFlag.from_enums(request_auth)

    # update auth
    request_auth = list(map(models.PTeamAuthEnum, ["invite", "admin"]))
    request = [
        {
            "user_id": str(user2.user_id),
            "authorities": request_auth,
        }
    ]
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER1), json=request
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == len(request)
    assert data[0]["user_id"] == str(user2.user_id)
    assert set(data[0]["authorities"]) == set(request_auth)
    row_user2 = (
        testdb.query(models.PTeamAuthority)
        .filter(
            models.PTeamAuthority.pteam_id == str(pteam1.pteam_id),
            models.PTeamAuthority.user_id == str(user2.user_id),
        )
        .one()
    )
    assert row_user2.authority == models.PTeamAuthIntFlag.from_enums(request_auth)


def test_update_pteam_auth__without_auth(testdb):
    user1 = create_user(USER1)
    user2 = create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)

    row_user1 = (
        testdb.query(models.PTeamAuthority)
        .filter(
            models.PTeamAuthority.pteam_id == str(pteam1.pteam_id),
            models.PTeamAuthority.user_id == str(user1.user_id),
        )
        .one()
    )
    assert row_user1.authority & models.PTeamAuthIntFlag.ADMIN

    request = [
        {
            "user_id": str(user2.user_id),
            "authorities": None,
        }
    ]
    response = client.post(f"/pteams/{pteam1.pteam_id}/authority", json=request)  # no headers
    assert response.status_code == 401
    assert response.reason_phrase == "Unauthorized"


def test_update_pteam_auth__without_authority():
    user1 = create_user(USER1)
    create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)

    # invite another as ADMIN (removing last ADMIN is not allowed)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id, ["admin"])
    accept_pteam_invitation(USER2, invitation.invitation_id)

    # remove ADMIN from user1
    request_auth = list(map(models.PTeamAuthEnum, ["invite"]))
    request = [
        {
            "user_id": str(user1.user_id),
            "authorities": request_auth,
        }
    ]
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER1), json=request
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == len(request)
    assert data[0]["user_id"] == str(user1.user_id)
    assert set(data[0]["authorities"]) == set(request_auth)

    # update without authority
    request_auth = list(map(models.PTeamAuthEnum, ["admin"]))
    request = [
        {
            "user_id": str(user1.user_id),
            "authorities": request_auth,
        }
    ]
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER1), json=request
    )
    assert response.status_code == 403
    assert response.reason_phrase == "Forbidden"


def test_update_pteam_auth__pseudo_uuid(testdb):
    user1 = create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)

    # initial values
    row_user1 = (
        testdb.query(models.PTeamAuthority)
        .filter(
            models.PTeamAuthority.pteam_id == str(pteam1.pteam_id),
            models.PTeamAuthority.user_id == str(user1.user_id),
        )
        .one()
    )
    assert row_user1.authority == models.PTeamAuthIntFlag.PTEAM_MASTER  # pteam master
    row_member = (
        testdb.query(models.PTeamAuthority)
        .filter(
            models.PTeamAuthority.pteam_id == str(pteam1.pteam_id),
            models.PTeamAuthority.user_id == str(MEMBER_UUID),
        )
        .one_or_none()
    )
    if row_member:
        assert row_member.authority == models.PTeamAuthIntFlag.PTEAM_MEMBER  # pteam member
    row_not_member = (
        testdb.query(models.PTeamAuthority)
        .filter(
            models.PTeamAuthority.pteam_id == str(pteam1.pteam_id),
            models.PTeamAuthority.user_id == str(NOT_MEMBER_UUID),
        )
        .one_or_none()
    )
    if row_not_member:
        assert row_not_member.authority == models.PTeamAuthIntFlag.FREE_TEMPLATE  # not member

    # update MEMBER & NOT_MEMBER
    member_auth = list(map(models.PTeamAuthEnum, ["topic_status"]))
    not_member_auth = list(map(models.PTeamAuthEnum, ["topic_status"]))
    request = [
        {"user_id": str(MEMBER_UUID), "authorities": member_auth},
        {"user_id": str(NOT_MEMBER_UUID), "authorities": not_member_auth},
    ]
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER1), json=request
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 2
    resp_map = {x["user_id"]: x for x in response.json()}
    resp_member = resp_map[str(MEMBER_UUID)]
    assert set(resp_member["authorities"]) == set(member_auth)
    resp_not_member = resp_map[str(NOT_MEMBER_UUID)]
    assert set(resp_not_member["authorities"]) == set(not_member_auth)
    row_member = (
        testdb.query(models.PTeamAuthority)
        .filter(
            models.PTeamAuthority.pteam_id == str(pteam1.pteam_id),
            models.PTeamAuthority.user_id == str(MEMBER_UUID),
        )
        .one()
    )
    assert row_member.authority == models.PTeamAuthIntFlag.from_enums(member_auth)
    row_not_member = (
        testdb.query(models.PTeamAuthority)
        .filter(
            models.PTeamAuthority.pteam_id == str(pteam1.pteam_id),
            models.PTeamAuthority.user_id == str(NOT_MEMBER_UUID),
        )
        .one()
    )
    assert row_not_member.authority == models.PTeamAuthIntFlag.from_enums(not_member_auth)


def test_update_pteam_auth__not_member(testdb):
    create_user(USER1)
    user2 = create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)

    # before joining
    row_user2 = (
        testdb.query(models.PTeamAuthority)
        .filter(
            models.PTeamAuthority.pteam_id == str(pteam1.pteam_id),
            models.PTeamAuthority.user_id == str(user2.user_id),
        )
        .one_or_none()
    )
    assert row_user2 is None

    # give auth to not member
    request_auth = list(map(models.PTeamAuthEnum, ["topic_status"]))
    request = [
        {
            "user_id": str(user2.user_id),
            "authorities": request_auth,
        }
    ]
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER1), json=request
    )
    assert response.status_code == 400
    assert response.reason_phrase == "Bad Request"

    # invite to pteam
    request_auth2 = list(map(models.PTeamAuthEnum, ["topic_status", "invite"]))
    invitation = invite_to_pteam(USER1, pteam1.pteam_id, request_auth2)
    accept_pteam_invitation(USER2, invitation.invitation_id)
    row_user2 = (
        testdb.query(models.PTeamAuthority)
        .filter(
            models.PTeamAuthority.pteam_id == str(pteam1.pteam_id),
            models.PTeamAuthority.user_id == str(user2.user_id),
        )
        .one()
    )
    assert row_user2.authority == models.PTeamAuthIntFlag.from_enums(request_auth2)


def test_update_pteam_auth__pseudo(testdb):
    create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)

    row_member = (
        testdb.query(models.PTeamAuthority)
        .filter(
            models.PTeamAuthority.pteam_id == str(pteam1.pteam_id),
            models.PTeamAuthority.user_id == str(MEMBER_UUID),
        )
        .one_or_none()
    )
    if row_member:
        assert row_member.authority == models.PTeamAuthIntFlag.PTEAM_MEMBER
    row_not_member = (
        testdb.query(models.PTeamAuthority)
        .filter(
            models.PTeamAuthority.pteam_id == str(pteam1.pteam_id),
            models.PTeamAuthority.user_id == str(NOT_MEMBER_UUID),
        )
        .one_or_none()
    )
    if row_not_member:
        assert row_not_member.authority == models.PTeamAuthIntFlag.FREE_TEMPLATE

    member_auth = list(map(models.PTeamAuthEnum, ["invite", "topic_status"]))
    not_member_auth = list(map(models.PTeamAuthEnum, ["topic_status"]))
    request = [
        {"user_id": str(MEMBER_UUID), "authorities": member_auth},
        {"user_id": str(NOT_MEMBER_UUID), "authorities": not_member_auth},
    ]
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER1), json=request
    )
    assert response.status_code == 200
    auth_map = {x["user_id"]: x["authorities"] for x in response.json()}
    assert set(auth_map[str(MEMBER_UUID)]) == set(member_auth)
    assert set(auth_map[str(NOT_MEMBER_UUID)]) == set(not_member_auth)

    row_member = (
        testdb.query(models.PTeamAuthority)
        .filter(
            models.PTeamAuthority.pteam_id == str(pteam1.pteam_id),
            models.PTeamAuthority.user_id == str(MEMBER_UUID),
        )
        .one_or_none()
    )
    assert row_member.authority == models.PTeamAuthIntFlag.from_enums(member_auth)
    row_not_member = (
        testdb.query(models.PTeamAuthority)
        .filter(
            models.PTeamAuthority.pteam_id == str(pteam1.pteam_id),
            models.PTeamAuthority.user_id == str(NOT_MEMBER_UUID),
        )
        .one_or_none()
    )
    assert row_not_member.authority == models.PTeamAuthIntFlag.from_enums(not_member_auth)


def test_update_pteam_auth__pseudo_admin():
    create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)

    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority",
        headers=headers(USER1),
        json=[{"user_id": str(MEMBER_UUID), "authorities": ["admin"]}],
    )
    assert response.status_code == 400
    assert response.reason_phrase == "Bad Request"

    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority",
        headers=headers(USER1),
        json=[{"user_id": str(NOT_MEMBER_UUID), "authorities": ["admin"]}],
    )
    assert response.status_code == 400
    assert response.reason_phrase == "Bad Request"


def test_update_pteam_auth__remove_admin__last():
    user1 = create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)

    # remove last admin
    request = [
        {"user_id": str(user1.user_id), "authorities": []},
    ]
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER1), json=request
    )
    assert response.status_code == 400
    assert response.reason_phrase == "Bad Request"
    assert response.json()["detail"] == "Removing last ADMIN is not allowed"


def test_update_pteam_auth__remove_admin__another():
    user1 = create_user(USER1)
    user2 = create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)
    # invite another admin
    invitation = invite_to_pteam(USER1, pteam1.pteam_id, ["admin"])
    accept_pteam_invitation(USER2, invitation.invitation_id)

    # try removing (no more last) admin
    request = [
        {"user_id": str(user1.user_id), "authorities": []},
    ]
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER1), json=request
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["authorities"] == []

    # come back admin
    request = [
        {"user_id": str(user1.user_id), "authorities": ["admin"]},
    ]
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER2), json=request
    )
    assert response.status_code == 200

    # remove all admins
    request = [
        {"user_id": str(user1.user_id), "authorities": []},
        {"user_id": str(user2.user_id), "authorities": []},
    ]
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER1), json=request
    )
    assert response.status_code == 400
    assert response.reason_phrase == "Bad Request"
    assert response.json()["detail"] == "Removing last ADMIN is not allowed"


def test_update_pteam_auth__swap_admin():
    user1 = create_user(USER1)
    user2 = create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)
    accept_pteam_invitation(USER2, invitation.invitation_id)

    request = [
        {"user_id": str(user1.user_id), "authorities": []},  # retire ADMIN
        {"user_id": str(user2.user_id), "authorities": ["admin"]},  # be ADMIN
    ]
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER1), json=request
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data) == len(request)
    auth_map = {x["user_id"]: x for x in data}
    old_admin = auth_map.get(str(user1.user_id))
    assert old_admin["authorities"] == []
    new_admin = auth_map.get(str(user2.user_id))
    assert new_admin["authorities"] == ["admin"]


def test_get_pteam_auth():
    user1 = create_user(USER1)  # master
    user2 = create_user(USER2)  # member
    create_user(USER3)  # not member
    pteam1 = create_pteam(USER1, PTEAM1)
    invite_auth = list(map(models.PTeamAuthEnum, ["topic_status"]))
    invitation = invite_to_pteam(USER1, pteam1.pteam_id, invite_auth)
    accept_pteam_invitation(USER2, invitation.invitation_id)

    # set pteam auth
    member_auth = list(map(models.PTeamAuthEnum, ["topic_status"]))
    not_member_auth = list(map(models.PTeamAuthEnum, ["topic_status"]))
    request = [
        {"user_id": str(MEMBER_UUID), "authorities": member_auth},
        {"user_id": str(NOT_MEMBER_UUID), "authorities": not_member_auth},
    ]
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER1), json=request
    )
    assert response.status_code == 200

    # get by master -> all member's auth & members auth
    response = client.get(f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER1))
    assert response.status_code == 200
    auth_map = {x["user_id"]: x["authorities"] for x in response.json()}
    assert set(auth_map.keys()) == set(
        map(str, [user1.user_id, user2.user_id, MEMBER_UUID, NOT_MEMBER_UUID])
    )
    assert set(auth_map[str(user1.user_id)]) == set(
        models.PTeamAuthIntFlag(models.PTeamAuthIntFlag.PTEAM_MASTER).to_enums()
    )
    assert set(auth_map.get(str(user2.user_id))) == set(invite_auth)
    assert set(auth_map.get(str(MEMBER_UUID))) == set(member_auth)
    assert set(auth_map.get(str(NOT_MEMBER_UUID))) == set(not_member_auth)

    # get by member -> all member's auth & members auth
    response = client.get(f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER2))
    assert response.status_code == 200
    auth_map = {x["user_id"]: x["authorities"] for x in response.json()}
    assert set(auth_map.keys()) == set(
        map(str, [user1.user_id, user2.user_id, MEMBER_UUID, NOT_MEMBER_UUID])
    )
    assert set(auth_map[str(user1.user_id)]) == set(
        models.PTeamAuthIntFlag(models.PTeamAuthIntFlag.PTEAM_MASTER).to_enums()
    )
    assert set(auth_map.get(str(user2.user_id))) == set(invite_auth)
    assert set(auth_map.get(str(MEMBER_UUID))) == set(member_auth)
    assert set(auth_map.get(str(NOT_MEMBER_UUID))) == set(not_member_auth)

    # get by not member -> not-member auth only
    response = client.get(f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER3))
    assert response.status_code == 200
    auth_map = {x["user_id"]: x["authorities"] for x in response.json()}
    assert set(auth_map.keys()) == set(map(str, [NOT_MEMBER_UUID]))
    assert set(auth_map.get(str(NOT_MEMBER_UUID))) == set(not_member_auth)


def test_get_pteam_auth__without_auth():
    create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)

    response = client.get(f"/pteams/{pteam1.pteam_id}/authority")  # no headers
    assert response.status_code == 401
    assert response.reason_phrase == "Unauthorized"


def test_pteam_auth_effects__indivudual():
    create_user(USER1)
    user2 = create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)  # no INVITE
    accept_pteam_invitation(USER2, invitation.invitation_id)

    with pytest.raises(HTTPError, match="403: Forbidden"):
        invite_to_pteam(USER2, pteam1.pteam_id)

    # give INVITE
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority",
        headers=headers(USER1),
        json=[{"user_id": str(user2.user_id), "authorities": ["invite"]}],
    )
    assert response.status_code == 200

    # try again
    invitation = invite_to_pteam(USER2, pteam1.pteam_id)
    assert invitation.invitation_id != ZERO_FILLED_UUID


def test_pteam_auth_effects__pseudo_member():
    create_user(USER1)
    create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)  # no INVITE
    accept_pteam_invitation(USER2, invitation.invitation_id)

    with pytest.raises(HTTPError, match="403: Forbidden"):
        invite_to_pteam(USER2, pteam1.pteam_id)

    # give INVITE to MEMBER
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority",
        headers=headers(USER1),
        json=[{"user_id": str(MEMBER_UUID), "authorities": ["invite"]}],
    )
    assert response.status_code == 200

    # try again
    invitation = invite_to_pteam(USER2, pteam1.pteam_id)
    assert invitation.invitation_id != ZERO_FILLED_UUID


def test_pteam_auth_effects__pseudo_not_member():
    create_user(USER1)
    create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)  # no INVITE
    accept_pteam_invitation(USER2, invitation.invitation_id)

    with pytest.raises(HTTPError, match="403: Forbidden"):
        invite_to_pteam(USER2, pteam1.pteam_id)

    # give INVITE to NOT_MEMBER. it is also applied to members.
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority",
        headers=headers(USER1),
        json=[{"user_id": str(NOT_MEMBER_UUID), "authorities": ["invite"]}],
    )
    assert response.status_code == 200

    # try again
    invitation = invite_to_pteam(USER2, pteam1.pteam_id)
    assert invitation.invitation_id != ZERO_FILLED_UUID


def test_create_invitation():
    create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)  # master have INVITE & ADMIN

    request_auth = list(map(models.PTeamAuthEnum, ["invite"]))
    request = {
        "expiration": str(datetime(3000, 1, 1, 0, 0, 0, 0)),
        "limit_count": 1,
        "authorities": request_auth,
    }
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/invitation", headers=headers(USER1), json=request
    )
    assert response.status_code == 200
    data = response.json()
    assert datetime.fromisoformat(data["expiration"]) == datetime.fromisoformat(
        request["expiration"]
    )
    assert data["limit_count"] == request["limit_count"]
    assert set(data["authorities"]) == set(request["authorities"])


def test_create_invitation__without_authorities():
    create_user(USER1)
    user2 = create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id, ["topic_status"])  # no INVITE
    accept_pteam_invitation(USER2, invitation.invitation_id)

    # try without INVITE
    request = {
        "expiration": str(datetime(3000, 1, 1, 0, 0, 0, 0)),
        "limit_count": 1,
        "authorities": None,  # no authorities
    }
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/invitation", headers=headers(USER2), json=request
    )
    assert response.status_code == 403
    assert response.reason_phrase == "Forbidden"

    # give INVITE
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority",
        headers=headers(USER1),
        json=[{"user_id": str(user2.user_id), "authorities": ["invite"]}],
    )
    assert response.status_code == 200

    # try again with INVITE
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/invitation", headers=headers(USER2), json=request
    )
    assert response.status_code == 200
    data = response.json()
    assert datetime.fromisoformat(data["expiration"]) == datetime.fromisoformat(
        request["expiration"]
    )
    assert data["limit_count"] == request["limit_count"]
    assert data["authorities"] == []

    # try giving authorities only with INVITE (no ADMIN)
    request_auth = list(map(models.PTeamAuthEnum, ["topic_status"]))
    request = {
        "expiration": str(datetime(3000, 1, 1, 0, 0, 0, 0)),
        "limit_count": 1,
        "authorities": request_auth,
    }
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/invitation", headers=headers(USER2), json=request
    )
    assert response.status_code == 400
    assert response.reason_phrase == "Bad Request"

    # give INVITE & ADMIN
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority",
        headers=headers(USER1),
        json=[{"user_id": str(user2.user_id), "authorities": ["invite", "admin"]}],
    )
    assert response.status_code == 200

    # try again with INVITE & ADMIN
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/invitation", headers=headers(USER2), json=request
    )
    assert response.status_code == 200
    data = response.json()
    assert datetime.fromisoformat(data["expiration"]) == datetime.fromisoformat(
        request["expiration"]
    )
    assert data["limit_count"] == request["limit_count"]
    assert set(data["authorities"]) == set(request["authorities"])


def test_create_invitation__by_not_member():
    create_user(USER1)
    create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)
    create_pteam(USER2, PTEAM2)

    # user2 is ADMIN of another pteam.
    request_auth = list(map(models.PTeamAuthEnum, ["invite"]))
    request = {
        "expiration": str(datetime(3000, 1, 1, 0, 0, 0, 0)),
        "limit_count": 1,
        "authorities": request_auth,
    }
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/invitation", headers=headers(USER2), json=request
    )
    assert response.status_code == 403
    assert response.reason_phrase == "Forbidden"


def test_create_invitation__wrong_params():
    create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)

    # wrong limit
    request_auth = list(map(models.PTeamAuthEnum, ["topic_status"]))
    request = {
        "expiration": str(datetime(3000, 1, 1, 0, 0, 0, 0)),
        "limit_count": 0,  # out of limit
        "authorities": request_auth,
    }
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/invitation", headers=headers(USER1), json=request
    )
    assert response.status_code == 400
    assert response.reason_phrase == "Bad Request"

    # past date
    request_auth = list(map(models.PTeamAuthEnum, ["topic_status"]))
    request = {
        "expiration": str(datetime(2000, 1, 1, 0, 0, 0, 0)),  # past date
        "limit_count": 1,
        "authorities": request_auth,
    }
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/invitation", headers=headers(USER1), json=request
    )
    assert response.status_code == 200  # past date is OK


def test_invited_pteam():
    user1 = create_user(USER1)
    create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)

    response = client.get(f"/pteams/invitation/{invitation.invitation_id}", headers=headers(USER2))
    assert response.status_code == 200
    data = response.json()
    assert UUID(data["pteam_id"]) == pteam1.pteam_id
    assert data["pteam_name"] == PTEAM1["pteam_name"]
    assert data["email"] == USER1["email"]
    assert UUID(data["user_id"]) == user1.user_id


def test_list_invitations():
    create_user(USER1)  # master, have INVITE & ADMIN
    create_user(USER2)  # member, not have INVITE
    create_user(USER3)  # member, have INVITE
    pteam1 = create_pteam(USER1, PTEAM1)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)
    accept_pteam_invitation(USER2, invitation.invitation_id)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id, ["invite"])
    accept_pteam_invitation(USER3, invitation.invitation_id)

    # create invitation
    request_auth = list(map(models.PTeamAuthEnum, ["topic_status"]))
    invitation1 = invite_to_pteam(USER1, pteam1.pteam_id, request_auth)

    # get by master
    response = client.get(f"/pteams/{pteam1.pteam_id}/invitation", headers=headers(USER1))
    assert response.status_code == 200
    assert len(response.json()) == 1  # invitation0 should be expired
    data = schemas.PTeamInvitationResponse(**response.json()[0])
    assert data.invitation_id == invitation1.invitation_id
    assert data.pteam_id == pteam1.pteam_id
    assert data.expiration == invitation1.expiration
    assert data.limit_count == invitation1.limit_count
    assert data.used_count == invitation1.used_count == 0
    assert set(data.authorities) == set(request_auth)

    # get without INVITE
    response = client.get(f"/pteams/{pteam1.pteam_id}/invitation", headers=headers(USER2))
    assert response.status_code == 403
    assert response.reason_phrase == "Forbidden"

    # get with INVITE, without ADMIN
    response = client.get(f"/pteams/{pteam1.pteam_id}/invitation", headers=headers(USER3))
    assert response.status_code == 200
    assert len(response.json()) == 1  # invitation0 should be expired
    data = schemas.PTeamInvitationResponse(**response.json()[0])
    assert data.invitation_id == invitation1.invitation_id
    assert data.pteam_id == pteam1.pteam_id
    assert data.expiration == invitation1.expiration
    assert data.limit_count == invitation1.limit_count
    assert data.used_count == invitation1.used_count == 0
    assert set(data.authorities) == set(request_auth)


def test_delete_invitation():
    create_user(USER1)  # master, have INVITE
    pteam1 = create_pteam(USER1, PTEAM1)
    invitation1 = invite_to_pteam(USER1, pteam1.pteam_id)

    response = client.get(f"/pteams/{pteam1.pteam_id}/invitation", headers=headers(USER1))
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["invitation_id"] == str(invitation1.invitation_id)

    response = client.delete(
        f"/pteams/{pteam1.pteam_id}/invitation/{invitation1.invitation_id}", headers=headers(USER1)
    )
    assert response.status_code == 204

    response = client.get(f"/pteams/{pteam1.pteam_id}/invitation", headers=headers(USER1))
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0


def test_delete_invitation__by_another():
    create_user(USER1)
    create_user(USER2)
    user3 = create_user(USER3)
    pteam1 = create_pteam(USER1, PTEAM1)

    target_invitation = invite_to_pteam(USER1, pteam1.pteam_id)

    response = client.get(f"/pteams/{pteam1.pteam_id}/invitation", headers=headers(USER1))
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["invitation_id"] == str(target_invitation.invitation_id)

    # delete by not pteam member
    response = client.delete(
        f"/pteams/{pteam1.pteam_id}/invitation/{target_invitation.invitation_id}",
        headers=headers(USER2),
    )
    assert response.status_code == 403
    assert response.reason_phrase == "Forbidden"

    # delete by pteam member without INVITE
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)  # no INVITE
    accept_pteam_invitation(USER3, invitation.invitation_id)
    response = client.delete(
        f"/pteams/{pteam1.pteam_id}/invitation/{target_invitation.invitation_id}",
        headers=headers(USER2),
    )
    assert response.status_code == 403

    # delete by pteam member with INVITE
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority",
        headers=headers(USER1),
        json=[{"user_id": str(user3.user_id), "authorities": ["invite"]}],
    )
    assert response.status_code == 200
    response = client.delete(
        f"/pteams/{pteam1.pteam_id}/invitation/{target_invitation.invitation_id}",
        headers=headers(USER3),
    )
    assert response.status_code == 204

    response = client.get(f"/pteams/{pteam1.pteam_id}/invitation", headers=headers(USER1))
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 0


def test_invitation_limit(testdb):
    # access to testdb directly to control expiration.
    create_user(USER1)
    create_user(USER2)
    create_user(USER3)
    pteam1 = create_pteam(USER1, PTEAM1)

    # expired
    invitation1 = invite_to_pteam(USER1, pteam1.pteam_id)
    response = client.get(f"/pteams/{pteam1.pteam_id}/invitation", headers=headers(USER1))
    assert response.status_code == 200
    assert len(response.json()) == 1
    row1 = (
        testdb.query(models.PTeamInvitation)
        .filter(models.PTeamInvitation.invitation_id == str(invitation1.invitation_id))
        .one()
    )
    row1.expiration = datetime(2000, 1, 1, 0, 0, 0, 0)  # past date
    testdb.add(row1)
    testdb.commit()
    response = client.get(f"/pteams/{pteam1.pteam_id}/invitation", headers=headers(USER1))
    assert response.status_code == 200
    assert len(response.json()) == 0  # expired
    with pytest.raises(HTTPError, match="400: Bad Request"):
        accept_pteam_invitation(USER2, invitation1.invitation_id)

    # used
    invitation2 = invite_to_pteam(USER1, pteam1.pteam_id)
    assert invitation2.limit_count == 1  # limited once
    accept_pteam_invitation(USER2, invitation2.invitation_id)
    with pytest.raises(HTTPError, match="400: Bad Request"):
        accept_pteam_invitation(USER3, invitation2.invitation_id)  # cannot use twice


def test_apply_invitation():
    user1 = create_user(USER1)
    user2 = create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)

    response = client.get(f"/pteams/{pteam1.pteam_id}/members", headers=headers(USER1))
    assert response.status_code == 200
    members = response.json()
    assert len(members) == 1
    assert set(x["user_id"] for x in members) == set(str(x.user_id) for x in [user1])
    response = client.get("/users/me", headers=headers(USER2))
    assert response.status_code == 200
    pteams = response.json()["pteams"]
    assert len(pteams) == 0
    response = client.get(f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER1))
    auth_map = {x["user_id"]: x for x in response.json()}
    assert auth_map.get(str(user2.user_id)) is None

    invitation = invite_to_pteam(USER1, pteam1.pteam_id)
    accept_pteam_invitation(USER2, invitation.invitation_id)

    response = client.get(f"/pteams/{pteam1.pteam_id}/members", headers=headers(USER1))
    assert response.status_code == 200
    members = response.json()
    assert len(members) == 2
    assert set(x["user_id"] for x in members) == set(str(x.user_id) for x in [user1, user2])
    response = client.get("/users/me", headers=headers(USER2))
    assert response.status_code == 200
    pteams = response.json()["pteams"]
    assert {UUID(pteam["pteam_id"]) for pteam in pteams} == {x.pteam_id for x in [pteam1]}
    response = client.get(f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER1))
    auth_map = {x["user_id"]: x for x in response.json()}
    assert auth_map.get(str(user2.user_id)) is None  # no individual auth


def test_apply_invitation__individual_auth():
    create_user(USER1)
    user2 = create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)
    request_auth = list(map(models.PTeamAuthEnum, ["topic_status", "invite"]))

    response = client.get(f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER1))
    auth_map = {x["user_id"]: x for x in response.json()}
    assert auth_map.get(str(user2.user_id)) is None

    invitation = invite_to_pteam(USER1, pteam1.pteam_id, request_auth)
    accept_pteam_invitation(USER2, invitation.invitation_id)

    response = client.get(f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER1))
    auth_map = {x["user_id"]: x for x in response.json()}
    assert set(auth_map.get(str(user2.user_id), {}).get("authorities", [])) == set(request_auth)


def test_delete_member__last_admin():
    user1 = create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)

    response = client.get("/users/me", headers=headers(USER1))
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(user1.user_id)
    assert {UUID(pteam["pteam_id"]) for pteam in data["pteams"]} == {pteam1.pteam_id}

    # try leaving the pteam
    response = client.delete(
        f"/pteams/{pteam1.pteam_id}/members/{user1.user_id}", headers=headers(USER1)
    )
    assert response.status_code == 400
    assert response.reason_phrase == "Bad Request"
    assert response.json()["detail"] == "Removing last ADMIN is not allowed"


def test_delete_member__last_admin_another():
    user1 = create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)

    response = client.get("/users/me", headers=headers(USER1))
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(user1.user_id)
    assert {UUID(pteam["pteam_id"]) for pteam in data["pteams"]} == {pteam1.pteam_id}

    # invite another member (not ADMIN)
    create_user(USER2)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)
    accept_pteam_invitation(USER2, invitation.invitation_id)

    # try leaving the pteam
    response = client.delete(
        f"/pteams/{pteam1.pteam_id}/members/{user1.user_id}", headers=headers(USER1)
    )
    assert response.status_code == 400
    assert response.reason_phrase == "Bad Request"
    assert response.json()["detail"] == "Removing last ADMIN is not allowed"


def test_delete_member__not_last_admin():
    user1 = create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)

    response = client.get("/users/me", headers=headers(USER1))
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(user1.user_id)
    assert {UUID(pteam["pteam_id"]) for pteam in data["pteams"]} == {pteam1.pteam_id}

    # invite another member (not ADMIN)
    user2 = create_user(USER2)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)
    accept_pteam_invitation(USER2, invitation.invitation_id)

    # make the other member ADMIN
    response = client.post(
        f"/pteams/{pteam1.pteam_id}/authority",
        headers=headers(USER1),
        json=[{"user_id": str(user2.user_id), "authorities": ["admin"]}],
    )
    assert response.status_code == 200

    # try leaving pteam
    response = client.delete(
        f"/pteams/{pteam1.pteam_id}/members/{user1.user_id}", headers=headers(USER1)
    )
    assert response.status_code == 204

    response = client.get("/users/me", headers=headers(USER1))
    assert response.status_code == 200
    data = response.json()
    assert data["user_id"] == str(user1.user_id)
    assert data["pteams"] == []

    # lost extra authorities on leaving.
    response = client.get(f"/pteams/{pteam1.pteam_id}/authority", headers=headers(USER2))
    assert response.status_code == 200
    auth_map = {x["user_id"]: x for x in response.json()}
    assert auth_map.get(str(user1.user_id)) is None


def test_delete_member__by_admin():
    user1 = create_user(USER1)
    user2 = create_user(USER2)
    user3 = create_user(USER3)
    pteam1 = create_pteam(USER1, PTEAM1)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)
    accept_pteam_invitation(USER2, invitation.invitation_id)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id, ["admin", "invite"])
    accept_pteam_invitation(USER3, invitation.invitation_id)

    # kickout the other ADMIN
    response = client.delete(
        f"/pteams/{pteam1.pteam_id}/members/{user1.user_id}", headers=headers(USER3)
    )
    assert response.status_code == 204

    # kickout member
    response = client.delete(
        f"/pteams/{pteam1.pteam_id}/members/{user2.user_id}", headers=headers(USER3)
    )
    assert response.status_code == 204

    # kickout myself
    response = client.delete(
        f"/pteams/{pteam1.pteam_id}/members/{user3.user_id}", headers=headers(USER3)
    )
    assert response.status_code == 400
    assert response.reason_phrase == "Bad Request"
    assert response.json()["detail"] == "Removing last ADMIN is not allowed"


def test_delete_member__by_admin_myself():
    create_user(USER1)
    user2 = create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)
    # invite another ADMIN
    invitation = invite_to_pteam(USER1, pteam1.pteam_id, ["admin"])
    accept_pteam_invitation(USER2, invitation.invitation_id)

    # kickout myself
    response = client.delete(
        f"/pteams/{pteam1.pteam_id}/members/{user2.user_id}", headers=headers(USER2)
    )
    assert response.status_code == 204


def test_delete_member__by_not_admin():
    user1 = create_user(USER1)
    user2 = create_user(USER2)
    user3 = create_user(USER3)
    pteam1 = create_pteam(USER1, PTEAM1)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)
    accept_pteam_invitation(USER2, invitation.invitation_id)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)
    accept_pteam_invitation(USER3, invitation.invitation_id)

    # kickout ADMIN
    response = client.delete(
        f"/pteams/{pteam1.pteam_id}/members/{user1.user_id}", headers=headers(USER3)
    )
    assert response.status_code == 403
    assert response.reason_phrase == "Forbidden"

    # kickout another member
    response = client.delete(
        f"/pteams/{pteam1.pteam_id}/members/{user2.user_id}", headers=headers(USER3)
    )
    assert response.status_code == 403
    assert response.reason_phrase == "Forbidden"

    # kickout myself
    response = client.delete(
        f"/pteams/{pteam1.pteam_id}/members/{user3.user_id}", headers=headers(USER3)
    )
    assert response.status_code == 204


def test_get_pteam_members():
    user1 = create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)

    response = client.get(f"/pteams/{pteam1.pteam_id}/members", headers=headers(USER1))
    assert response.status_code == 200
    members = response.json()
    assert len(members) == 1
    keys = ["user_id", "uid", "email", "disabled", "years"]
    for key in keys:
        assert str(members[0].get(key)) == str(getattr(user1, key))
    assert {UUID(pteam["pteam_id"]) for pteam in members[0]["pteams"]} == {pteam1.pteam_id}

    user2 = create_user(USER2)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)
    accept_pteam_invitation(USER2, invitation.invitation_id)

    response = client.get(f"/pteams/{pteam1.pteam_id}/members", headers=headers(USER1))
    assert response.status_code == 200
    members = response.json()
    assert len(members) == 2
    members_map = {UUID(x["user_id"]): x for x in members}
    keys = ["user_id", "uid", "email", "disabled", "years"]
    for key in keys:
        assert str(members_map.get(user1.user_id).get(key)) == str(getattr(user1, key))
        assert str(members_map.get(user2.user_id).get(key)) == str(getattr(user2, key))
    assert (
        {UUID(p["pteam_id"]) for p in members_map.get(user1.user_id).get("pteams", [])}
        == {UUID(p["pteam_id"]) for p in members_map.get(user2.user_id).get("pteams", [])}
        == {pteam1.pteam_id}
    )


def test_get_pteam_members__by_member():
    user1 = create_user(USER1)
    user2 = create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)
    accept_pteam_invitation(USER2, invitation.invitation_id)

    response = client.get(f"/pteams/{pteam1.pteam_id}/members", headers=headers(USER2))
    assert response.status_code == 200
    members = response.json()
    assert len(members) == 2
    members_map = {UUID(x["user_id"]): x for x in members}
    keys = ["user_id", "uid", "email", "disabled", "years"]
    for key in keys:
        assert str(members_map.get(user1.user_id).get(key)) == str(getattr(user1, key))
        assert str(members_map.get(user2.user_id).get(key)) == str(getattr(user2, key))
    assert (
        {UUID(p["pteam_id"]) for p in members_map.get(user1.user_id).get("pteams", [])}
        == {UUID(p["pteam_id"]) for p in members_map.get(user2.user_id).get("pteams", [])}
        == {pteam1.pteam_id}
    )


def test_get_pteam_members__by_not_member():
    create_user(USER1)
    create_user(USER2)
    pteam1 = create_pteam(USER1, PTEAM1)

    response = client.get(f"/pteams/{pteam1.pteam_id}/members", headers=headers(USER2))
    assert response.status_code == 403
    assert response.reason_phrase == "Forbidden"


def test_get_pteam_topics():
    user1 = create_user(USER1)
    create_user(USER2)
    create_tag(USER1, TAG1)
    pteam1 = create_pteam(USER1, PTEAM1)
    invitation = invite_to_pteam(USER1, pteam1.pteam_id)
    accept_pteam_invitation(USER2, invitation.invitation_id)

    # add tag1 to pteam1
    service_x = "service_x"
    refs0 = {TAG1: [("fake target 1", "fake version 1")]}
    upload_pteam_tags(USER1, pteam1.pteam_id, service_x, refs0)

    response = client.get(f"/pteams/{pteam1.pteam_id}/topics", headers=headers(USER2))
    assert response.status_code == 200
    assert response.json() == []

    now = datetime.now()
    create_topic(USER1, TOPIC1, actions=[ACTION2, ACTION1])  # TAG1

    response = client.get(f"/pteams/{pteam1.pteam_id}/topics", headers=headers(USER2))
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["topic_id"] == str(TOPIC1["topic_id"])
    assert data[0]["title"] == TOPIC1["title"]
    assert data[0]["abstract"] == TOPIC1["abstract"]
    assert data[0]["threat_impact"] == TOPIC1["threat_impact"]
    assert data[0]["created_by"] == str(user1.user_id)
    data0_created_at = datetime.fromisoformat(data[0]["created_at"])
    assert data0_created_at > now
    assert data0_created_at < now + timedelta(seconds=30)
    assert data[0]["created_at"] == data[0]["updated_at"]
    assert {x["tag_name"] for x in data[0]["tags"]} == set(TOPIC1["tags"])
    assert {x["tag_name"] for x in data[0]["misp_tags"]} == set(TOPIC1["misp_tags"])


def test_get_pteam_topics__by_not_member():
    create_user(USER1)
    create_user(USER2)
    create_tag(USER1, TAG1)
    pteam1 = create_pteam(USER1, PTEAM1)

    # add tag1 to pteam1
    service_x = "service_x"
    refs0 = {TAG1: [("fake target 1", "fake version 1")]}
    upload_pteam_tags(USER1, pteam1.pteam_id, service_x, refs0)

    response = client.get(f"/pteams/{pteam1.pteam_id}/topics", headers=headers(USER2))
    assert response.status_code == 403
    assert response.reason_phrase == "Forbidden"


def test_upload_pteam_tags_file():
    create_user(USER1)
    tag1 = create_tag(USER1, "alpha:alpha2:alpha3")
    pteam1 = create_pteam(USER1, PTEAM1)
    # To test multiple rows error, pteam2 is created for test
    create_pteam(USER1, PTEAM2)

    def _eval_upload_tags_file(blines_, params_) -> dict:
        with tempfile.NamedTemporaryFile(mode="w+t", suffix=".jsonl") as tfile:
            for bline in blines_:
                tfile.writelines(bline + "\n")
            tfile.flush()
            tfile.seek(0)
            with open(tfile.name, "rb") as bfile:
                return assert_200(
                    client.post(
                        f"/pteams/{pteam1.pteam_id}/upload_tags_file",
                        headers=file_upload_headers(USER1),
                        files={"file": bfile},
                        params=params_,
                    )
                )

    def _compare_ext_tags(_tag1: dict, _tag2: dict) -> bool:
        if not isinstance(_tag1, dict) or not isinstance(_tag2, dict):
            return False
        _keys = {"tag_name", "tag_id", "parent_name", "parent_id"}
        if any(_tag1.get(_key) != _tag2.get(_key) for _key in _keys):
            return False
        return compare_references(_tag1["references"], _tag1["references"])

    def _compare_responsed_tags(_tags1: list[dict], _tags2: list[dict]) -> bool:
        if not isinstance(_tags1, list) or not isinstance(_tags2, list):
            return False
        if len(_tags1) != len(_tags2):
            return False
        return all(_compare_ext_tags(_tags1[_idx], _tags2[_idx]) for _idx in range(len(_tags1)))

    params = {"service": "threatconnectome", "force_mode": True}

    # upload a line
    lines = [
        (
            '{"tag_name":"teststring",'
            '"references":[{"target":"api/Pipfile.lock","version":"1.0"}]}'
        )
    ]
    data = _eval_upload_tags_file(lines, params)
    tags = {tag["tag_name"]: tag for tag in data}
    assert len(tags) == 1
    assert "teststring" in tags
    assert compare_references(
        tags["teststring"]["references"],
        [{"service": params["service"], "target": "api/Pipfile.lock", "version": "1.0"}],
    )

    # upload 2 lines
    lines += [
        (
            '{"tag_name":"test1",'
            '"references":[{"target":"api/Pipfile.lock","version":"1.0"},'
            '{"target":"api3/Pipfile.lock","version":"0.1"}]}'
        )
    ]
    data = _eval_upload_tags_file(lines, params)
    tags = {tag["tag_name"]: tag for tag in data}
    assert len(tags) == 2
    assert "teststring" in tags
    assert "test1" in tags
    assert compare_references(
        tags["teststring"]["references"],
        [{"service": params["service"], "target": "api/Pipfile.lock", "version": "1.0"}],
    )
    assert compare_references(
        tags["test1"]["references"],
        [
            {"service": params["service"], "target": "api/Pipfile.lock", "version": "1.0"},
            {"service": params["service"], "target": "api3/Pipfile.lock", "version": "0.1"},
        ],
    )

    # upload duplicated lines
    lines += [
        (
            '{"tag_name":"test1",'
            '"references":[{"target":"api/Pipfile.lock","version":"1.0"},'
            '{"target":"api3/Pipfile.lock","version":"0.1"}]}'
        )
    ]
    data = _eval_upload_tags_file(lines, params)
    tags = {tag["tag_name"]: tag for tag in data}
    assert len(tags) == 2
    assert "teststring" in tags
    assert "test1" in tags
    assert compare_references(
        tags["teststring"]["references"],
        [{"service": params["service"], "target": "api/Pipfile.lock", "version": "1.0"}],
    )
    assert compare_references(
        tags["test1"]["references"],
        [
            {"service": params["service"], "target": "api/Pipfile.lock", "version": "1.0"},
            {"service": params["service"], "target": "api3/Pipfile.lock", "version": "0.1"},
        ],
    )

    # upload another lines
    lines = ['{"tag_name":"alpha:alpha2:alpha3", "references": [{"target": "", "version": ""}]}']
    data = _eval_upload_tags_file(lines, params)
    tags = {tag["tag_name"]: tag for tag in data}
    assert len(tags) == 1
    assert "alpha:alpha2:alpha3" in tags
    assert compare_references(
        tags["alpha:alpha2:alpha3"]["references"],
        [{"service": params["service"], "target": "", "version": ""}],
    )
    assert tags["alpha:alpha2:alpha3"]["tag_id"] == str(tag1.tag_id)  # already existed tag


def test_upload_pteam_tags_file__complex():
    create_user(USER1)
    tag_aaa = create_tag(USER1, "a:a:a")
    tag_bbb = create_tag(USER1, "b:b:b")
    pteam1 = create_pteam(USER1, {**PTEAM1, "tags": []})

    service_a = {"service": "service-a", "force_mode": True}
    service_b = {"service": "service-b", "force_mode": True}

    def _eval_upload_tags_file(lines_, params_) -> dict:
        with tempfile.NamedTemporaryFile(mode="w+t", suffix=".jsonl") as tfile:
            for line in lines_:
                tfile.writelines(json.dumps(line) + "\n")
            tfile.flush()
            tfile.seek(0)
            with open(tfile.name, "rb") as bfile:
                return assert_200(
                    client.post(
                        f"/pteams/{pteam1.pteam_id}/upload_tags_file",
                        headers=file_upload_headers(USER1),
                        files={"file": bfile},
                        params=params_,
                    )
                )

    def _compare_ext_tags(_tag1: dict, _tag2: dict) -> bool:
        if not isinstance(_tag1, dict) or not isinstance(_tag2, dict):
            return False
        _keys = {"tag_name", "tag_id", "parent_name", "parent_id"}
        if any(_tag1.get(_key) != _tag2.get(_key) for _key in _keys):
            return False
        return compare_references(_tag1["references"], _tag1["references"])

    def _compare_responsed_tags(_tags1: list[dict], _tags2: list[dict]) -> bool:
        if not isinstance(_tags1, list) or not isinstance(_tags2, list):
            return False
        if len(_tags1) != len(_tags2):
            return False
        return all(_compare_ext_tags(_tags1[_idx], _tags2[_idx]) for _idx in range(len(_tags1)))

    def _compare_tag_summaries(_tag1: dict, _tag2: dict) -> bool:
        if not isinstance(_tag1, dict) or not isinstance(_tag2, dict):
            return False
        _keys = {"threat_impact", "updated_at", "status_count"}
        if any(_tag1.get(_key) != _tag2.get(_key) for _key in _keys):
            return False
        return _compare_ext_tags(_tag1, _tag2)

    def _compare_summaries(_sum1: dict, _sum2: dict) -> bool:
        if not isinstance(_sum1, dict) or not isinstance(_sum2, dict):
            return False
        if _sum1.get("threat_impact_count") != _sum2.get("threat_impact_count"):
            return False
        if len(_sum1["tags"]) != len(_sum2["tags"]):
            return False
        return all(
            _compare_tag_summaries(_sum1["tags"][_idx], _sum2["tags"][_idx])
            for _idx in range(len(_sum1["tags"]))
        )

    # add a:a:a as service-a
    lines = [
        {
            "tag_name": tag_aaa.tag_name,
            "references": [{"target": "target1", "version": "1.0"}],
        },
    ]
    data = _eval_upload_tags_file(lines, service_a)
    exp1 = {
        **schema_to_dict(tag_aaa),
        "references": [
            {"target": "target1", "version": "1.0", "service": "service-a"},
        ],
    }
    assert _compare_responsed_tags(data, [exp1])

    # add b:b:b as service-b
    lines = [
        {
            "tag_name": tag_bbb.tag_name,
            "references": [
                {"target": "target2", "version": "1.0"},
                {"target": "target2", "version": "1.1"},  # multiple version in one target
            ],
        }
    ]
    data = _eval_upload_tags_file(lines, service_b)
    exp2 = {
        **schema_to_dict(tag_bbb),
        "references": [
            {"target": "target2", "version": "1.0", "service": "service-b"},
            {"target": "target2", "version": "1.1", "service": "service-b"},
        ],
    }
    assert _compare_responsed_tags(data, [exp1, exp2])

    # update service-a with b:b:b, without a:a:a
    lines = [
        {
            "tag_name": tag_bbb.tag_name,
            "references": [
                {"target": "target1", "version": "1.2"},
            ],
        }
    ]
    data = _eval_upload_tags_file(lines, service_a)
    exp3 = {
        **schema_to_dict(tag_bbb),
        "references": [
            *exp2["references"],
            {"target": "target1", "version": "1.2", "service": "service-a"},
        ],
    }
    assert _compare_responsed_tags(data, [exp3])


def test_upload_pteam_tags_file_with_empty_file():
    create_user(USER1)
    pteam = create_pteam(USER1, PTEAM1)

    params = {"service": "threatconnectome", "force_mode": True}
    tag_file = Path(__file__).resolve().parent / "upload_test" / "empty.jsonl"
    with open(tag_file, "rb") as tags:
        response = client.post(
            f"/pteams/{pteam.pteam_id}/upload_tags_file",
            headers=file_upload_headers(USER1),
            files={"file": tags},
            params=params,
        )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "Upload file is empty"


def test_upload_pteam_tags_file_with_wrong_filename():
    create_user(USER1)
    pteam = create_pteam(USER1, PTEAM1)

    params = {"service": "threatconnectome", "force_mode": True}
    tag_file = Path(__file__).resolve().parent / "upload_test" / "tag.txt"
    with open(tag_file, "rb") as tags:
        response = client.post(
            f"/pteams/{pteam.pteam_id}/upload_tags_file",
            headers=file_upload_headers(USER1),
            files={"file": tags},
            params=params,
        )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "Please upload a file with .jsonl as extension"


def test_upload_pteam_tags_file_without_tag_name():
    create_user(USER1)
    pteam = create_pteam(USER1, PTEAM1)

    params = {"service": "threatconnectome", "force_mode": True}
    tag_file = Path(__file__).resolve().parent / "upload_test" / "no_tag_key.jsonl"
    with open(tag_file, "rb") as tags:
        response = client.post(
            f"/pteams/{pteam.pteam_id}/upload_tags_file",
            headers=file_upload_headers(USER1),
            files={"file": tags},
            params=params,
        )
    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "Missing tag_name"


def test_upload_pteam_tags_file_with_wrong_content_format():
    create_user(USER1)
    pteam = create_pteam(USER1, PTEAM1)

    params = {"service": "threatconnectome", "force_mode": True}
    tag_file = Path(__file__).resolve().parent / "upload_test" / "tag_with_wrong_format.jsonl"
    with open(tag_file, "rb") as tags:
        with pytest.raises(HTTPError, match=r"400: Bad Request: Wrong file content"):
            assert_200(
                client.post(
                    f"/pteams/{pteam.pteam_id}/upload_tags_file",
                    headers=file_upload_headers(USER1),
                    files={"file": tags},
                    params=params,
                )
            )


def test_upload_pteam_tags_file_with_unexist_tagnames():
    create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)

    not_exist_tag_names = ["teststring", "test1", "test2", "test3"]
    refs = {tag_name: [("fake target", "fake version")] for tag_name in not_exist_tag_names}

    with pytest.raises(
        HTTPError,
        match=rf"400: Bad Request: No such tags: {', '.join(sorted(not_exist_tag_names))}",
    ):
        upload_pteam_tags(USER1, pteam1.pteam_id, "threatconnectome", refs, force_mode=False)


def test_service_tagged_ticket_ids_with_wrong_pteam_id(testdb):
    # create current_ticket_status table
    ticket_response = ticket_utils.create_ticket(testdb, USER1, PTEAM1, TOPIC1)

    json_data = {
        "topic_status": "acknowledged",
        "note": "string",
        "assignees": [],
        "scheduled_at": str(datetime.now()),
    }
    create_service_topicstatus(
        USER1,
        ticket_response["pteam_id"],
        ticket_response["service_id"],
        ticket_response["topic_id"],
        ticket_response["tag_id"],
        json_data,
    )

    # with wrong pteam_id
    pteam_id = str(uuid4())
    response = client.get(
        f"/pteams/{pteam_id}/services/{ticket_response['service_id']}/tags/{ticket_response['tag_id']}/topic_ids",
        headers=headers(USER1),
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "No such pteam"}


def test_service_tagged_ticket_ids_with_wrong_pteam_member(testdb):
    # create current_ticket_status table
    ticket_response = ticket_utils.create_ticket(testdb, USER1, PTEAM1, TOPIC1)

    json_data = {
        "topic_status": "acknowledged",
        "note": "string",
        "assignees": [],
        "scheduled_at": str(datetime.now()),
    }
    create_service_topicstatus(
        USER1,
        ticket_response["pteam_id"],
        ticket_response["service_id"],
        ticket_response["topic_id"],
        ticket_response["tag_id"],
        json_data,
    )

    # with wrong pteam member
    create_user(USER2)
    response = client.get(
        f"/pteams/{ticket_response['pteam_id']}/services/{ticket_response['service_id']}/tags/{ticket_response['tag_id']}/topic_ids",
        headers=headers(USER2),
    )
    assert response.status_code == 403
    assert response.json() == {"detail": "Not a pteam member"}


def test_service_tagged_ticket_ids_with_wrong_service_id(testdb):
    # create current_ticket_status table
    ticket_response = ticket_utils.create_ticket(testdb, USER1, PTEAM1, TOPIC1)

    json_data = {
        "topic_status": "acknowledged",
        "note": "string",
        "assignees": [],
        "scheduled_at": str(datetime.now()),
    }
    create_service_topicstatus(
        USER1,
        ticket_response["pteam_id"],
        ticket_response["service_id"],
        ticket_response["topic_id"],
        ticket_response["tag_id"],
        json_data,
    )

    # with wrong service_id
    service_id = str(uuid4())
    response = client.get(
        f"/pteams/{ticket_response['pteam_id']}/services/{service_id}/tags/{ticket_response['tag_id']}/topic_ids",
        headers=headers(USER1),
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "No such service"}


def test_service_tagged_ticket_ids_with_service_not_in_pteam(testdb):
    # create current_ticket_status table
    ticket_response1 = ticket_utils.create_ticket(testdb, USER1, PTEAM1, TOPIC1)
    ticket_response2 = ticket_utils.create_ticket(testdb, USER2, PTEAM2, TOPIC2)

    json_data = {
        "topic_status": "acknowledged",
        "note": "string",
        "assignees": [],
        "scheduled_at": str(datetime.now()),
    }
    create_service_topicstatus(
        USER1,
        ticket_response1["pteam_id"],
        ticket_response1["service_id"],
        ticket_response1["topic_id"],
        ticket_response1["tag_id"],
        json_data,
    )

    # with service not in pteam
    response = client.get(
        f"/pteams/{ticket_response1['pteam_id']}/services/{ticket_response2['service_id']}/tags/{ticket_response1['tag_id']}/topic_ids",
        headers=headers(USER1),
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "No such service"}


def test_service_tagged_tikcet_ids_with_wrong_tag_id(testdb):
    # create current_ticket_status table
    ticket_response = ticket_utils.create_ticket(testdb, USER1, PTEAM1, TOPIC1)

    json_data = {
        "topic_status": "acknowledged",
        "note": "string",
        "assignees": [],
        "scheduled_at": str(datetime.now()),
    }
    create_service_topicstatus(
        USER1,
        ticket_response["pteam_id"],
        ticket_response["service_id"],
        ticket_response["topic_id"],
        ticket_response["tag_id"],
        json_data,
    )

    # with wrong tag_id
    tag_id = str(uuid4())
    response = client.get(
        f"/pteams/{ticket_response['pteam_id']}/services/{ticket_response['service_id']}/tags/{tag_id}/topic_ids",
        headers=headers(USER1),
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "No such tag"}


def test_service_tagged_ticket_ids_with_valid_but_not_service_tag(testdb):
    # create current_ticket_status table
    ticket_response1 = ticket_utils.create_ticket(testdb, USER1, PTEAM1, TOPIC1)

    json_data = {
        "topic_status": "acknowledged",
        "note": "string",
        "assignees": [],
        "scheduled_at": str(datetime.now()),
    }
    create_service_topicstatus(
        USER1,
        ticket_response1["pteam_id"],
        ticket_response1["service_id"],
        ticket_response1["topic_id"],
        ticket_response1["tag_id"],
        json_data,
    )

    # with valid but not service tag
    str1 = "a1:a2:a3"
    tag = create_tag(USER1, str1)
    response = client.get(
        f"/pteams/{ticket_response1['pteam_id']}/services/{ticket_response1['service_id']}/tags/{tag.tag_id}/topic_ids",
        headers=headers(USER1),
    )
    assert response.status_code == 404
    assert response.json() == {"detail": "No such service tag"}


def test_remove_pteamtags_by_service():
    create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)
    service1 = "threatconnectome"
    service2 = "flashsense"

    refs0 = {TAG1: [("fake target", "fake version")]}
    upload_pteam_tags(USER1, pteam1.pteam_id, service1, refs0)
    response2 = upload_pteam_tags(USER1, pteam1.pteam_id, service2, refs0)

    for tag in response2:
        for reference in tag.references:
            assert reference["service"] in [service1, service2]

    assert_204(
        client.delete(
            f"/pteams/{pteam1.pteam_id}/tags",
            headers=headers(USER1),
            params={"service": service1},
        )
    )


def test_get_watchers():
    create_user(USER1)
    create_user(USER2)
    create_user(USER3)
    ateam1 = create_ateam(USER1, ATEAM1)
    pteam1 = create_pteam(USER1, PTEAM1)

    data = assert_200(client.get(f"/pteams/{pteam1.pteam_id}/watchers", headers=headers(USER1)))
    assert len(data) == 0

    watching_request1 = create_watching_request(USER1, ateam1.ateam_id)
    accept_watching_request(USER1, watching_request1.request_id, pteam1.pteam_id)

    data = assert_200(client.get(f"/pteams/{pteam1.pteam_id}/watchers", headers=headers(USER1)))
    assert len(data) == 1
    assert data[0]["ateam_id"] == str(ateam1.ateam_id)

    invitation = invite_to_pteam(USER1, pteam1.pteam_id)
    accept_pteam_invitation(USER2, invitation.invitation_id)

    # get by member
    data = assert_200(client.get(f"/pteams/{pteam1.pteam_id}/watchers", headers=headers(USER2)))
    assert len(data) == 1
    assert data[0]["ateam_id"] == str(ateam1.ateam_id)

    # get by not member
    with pytest.raises(HTTPError, match=r"403: Forbidden: Not a pteam member"):
        assert_200(client.get(f"/pteams/{pteam1.pteam_id}/watchers", headers=headers(USER3)))


def test_remove_watcher():
    create_user(USER1)
    create_user(USER2)
    create_user(USER3)
    ateam1 = create_ateam(USER1, ATEAM1)
    pteam1 = create_pteam(USER1, PTEAM1)

    invitation = invite_to_pteam(USER1, pteam1.pteam_id)
    accept_pteam_invitation(USER2, invitation.invitation_id)

    watching_request = create_watching_request(USER1, ateam1.ateam_id)
    accept_watching_request(USER1, watching_request.request_id, pteam1.pteam_id)

    data = assert_200(client.get(f"/pteams/{pteam1.pteam_id}/watchers", headers=headers(USER1)))
    assert len(data) == 1

    # delete by not member
    with pytest.raises(HTTPError, match=r"403: Forbidden: You do not have authority"):
        assert_200(
            client.delete(
                f"/pteams/{pteam1.pteam_id}/watchers/{ateam1.ateam_id}", headers=headers(USER3)
            )
        )

    # delete by not ADMIN
    with pytest.raises(HTTPError, match=r"403: Forbidden: You do not have authority"):
        assert_200(
            client.delete(
                f"/pteams/{pteam1.pteam_id}/watchers/{ateam1.ateam_id}", headers=headers(USER2)
            )
        )

    # delete by ADMIN
    response = client.delete(
        f"/pteams/{pteam1.pteam_id}/watchers/{ateam1.ateam_id}", headers=headers(USER1)
    )
    assert response.status_code == 204
    data = assert_200(client.get(f"/pteams/{pteam1.pteam_id}/watchers", headers=headers(USER1)))
    assert len(data) == 0
    data = assert_200(
        client.get(f"/ateams/{ateam1.ateam_id}/watching_pteams", headers=headers(USER1))
    )
    assert len(data) == 0


def test_upload_pteam_sbom_file_with_syft():
    create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)
    # To avoid multiple rows error, pteam2 is created for test
    create_pteam(USER1, PTEAM2)

    params = {"service": "threatconnectome", "force_mode": True}
    sbom_file = Path(__file__).resolve().parent / "upload_test" / "test_syft_cyclonedx.json"
    with open(sbom_file, "rb") as tags:
        response = client.post(
            f"/pteams/{pteam1.pteam_id}/upload_sbom_file",
            headers=file_upload_headers(USER1),
            params=params,
            files={"file": tags},
        )
    assert response.status_code == 200
    data = response.json()
    assert data["pteam_id"] == str(pteam1.pteam_id)
    assert data["service_name"] == params["service"]
    assert data["sbom_file_sha256"] == calc_file_sha256(sbom_file)


def test_upload_pteam_sbom_file_with_trivy():
    create_user(USER1)
    pteam1 = create_pteam(USER1, PTEAM1)
    # To avoid multiple rows error, pteam2 is created for test
    create_pteam(USER1, PTEAM2)

    params = {"service": "threatconnectome", "force_mode": True}
    sbom_file = Path(__file__).resolve().parent / "upload_test" / "test_trivy_cyclonedx.json"
    with open(sbom_file, "rb") as tags:
        response = client.post(
            f"/pteams/{pteam1.pteam_id}/upload_sbom_file",
            headers=file_upload_headers(USER1),
            params=params,
            files={"file": tags},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["pteam_id"] == str(pteam1.pteam_id)
    assert data["service_name"] == params["service"]
    assert data["sbom_file_sha256"] == calc_file_sha256(sbom_file)


def test_upload_pteam_sbom_file_with_empty_file():
    create_user(USER1)
    pteam = create_pteam(USER1, PTEAM1)

    params = {"service": "threatconnectome", "force_mode": True}
    sbom_file = Path(__file__).resolve().parent / "upload_test" / "empty.json"
    with open(sbom_file, "rb") as tags:
        response = client.post(
            f"/pteams/{pteam.pteam_id}/upload_sbom_file",
            headers=file_upload_headers(USER1),
            params=params,
            files={"file": tags},
        )

    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "Upload file is empty"


def test_upload_pteam_sbom_file_with_wrong_filename():
    create_user(USER1)
    pteam = create_pteam(USER1, PTEAM1)

    params = {"service": "threatconnectome", "force_mode": True}
    sbom_file = Path(__file__).resolve().parent / "upload_test" / "tag.txt"
    with open(sbom_file, "rb") as tags:
        response = client.post(
            f"/pteams/{pteam.pteam_id}/upload_sbom_file",
            headers=file_upload_headers(USER1),
            params=params,
            files={"file": tags},
        )

    assert response.status_code == 400
    data = response.json()
    assert data["detail"] == "Please upload a file with .json as extension"


def test_it_should_return_422_when_upload_sbom_with_over_255_char_servicename():
    create_user(USER1)
    pteam = create_pteam(USER1, PTEAM1)

    # create 256 alphanumeric characters
    service_name = "a" * 256

    params = {"service": service_name, "force_mode": True}
    sbom_file = Path(__file__).resolve().parent / "upload_test" / "test_trivy_cyclonedx.json"
    with open(sbom_file, "rb") as tags:
        response = client.post(
            f"/pteams/{pteam.pteam_id}/upload_sbom_file",
            headers=file_upload_headers(USER1),
            params=params,
            files={"file": tags},
        )

    assert response.status_code == 422
    data = response.json()
    assert data["detail"] == "Length of Service name exceeds 255 characters"


@pytest.mark.skip(reason="TODO: need api to get background task status")
def test_upload_pteam_sbom_file_wrong_content_format():
    create_user(USER1)
    pteam = create_pteam(USER1, PTEAM1)

    params = {"service": "threatconnectome", "force_mode": True}
    sbom_file = Path(__file__).resolve().parent / "upload_test" / "tag_with_wrong_format.json"
    with open(sbom_file, "rb") as tags:
        with pytest.raises(HTTPError, match=r"400: Bad Request: Not supported file format"):
            assert_200(
                client.post(
                    f"/pteams/{pteam.pteam_id}/upload_sbom_file",
                    headers=file_upload_headers(USER1),
                    params=params,
                    files={"file": tags},
                )
            )


def test_get_service_topic_status_without_ticket_status(testdb: Session):
    threat = threat_utils.create_threat(testdb, USER1, PTEAM1, TOPIC1, ACTION1)
    dependency = (
        testdb.query(models.Dependency)
        .filter(
            models.Dependency.dependency_id == str(threat.dependency_id),
        )
        .one()
    )
    pteam_id = dependency.service.pteam.pteam_id
    service_id = UUID(dependency.service.service_id)
    tag_id = UUID(dependency.tag.tag_id)

    response = client.get(
        f"/pteams/{pteam_id}/services/{service_id}/topicstatus/{threat.topic_id}/{tag_id}",
        headers=headers(USER1),
    )
    assert response.status_code == 200
    responsed_topicstatuses = response.json()
    assert responsed_topicstatuses["pteam_id"] == str(pteam_id)
    assert responsed_topicstatuses["service_id"] == str(service_id)
    assert responsed_topicstatuses["topic_id"] == str(threat.topic_id)
    assert responsed_topicstatuses["tag_id"] == str(tag_id)
    assert responsed_topicstatuses["user_id"] is None
    assert responsed_topicstatuses["topic_status"] is None
    assert responsed_topicstatuses["note"] is None


def test_get_service_topic_status_with_ticket_status(testdb: Session):
    threat = threat_utils.create_threat(testdb, USER1, PTEAM1, TOPIC1, ACTION1)
    dependency = (
        testdb.query(models.Dependency)
        .filter(
            models.Dependency.dependency_id == str(threat.dependency_id),
        )
        .one()
    )
    pteam_id = dependency.service.pteam.pteam_id
    service_id = UUID(dependency.service.service_id)
    tag_id = UUID(dependency.tag.tag_id)

    set_request = {
        "topic_status": models.TopicStatusType.acknowledged,
        "logging_ids": [],
        "assignees": [],
        "note": f"acknowledged by {USER1['email']}",
        "scheduled_at": None,
    }
    create_service_topicstatus(
        USER1,
        pteam_id,
        service_id,
        threat.topic_id,
        tag_id,
        set_request,
    )

    # get topicstatuses
    response = client.get(
        f"/pteams/{pteam_id}/services/{service_id}/topicstatus/{threat.topic_id}/{tag_id}",
        headers=headers(USER1),
    )
    assert response.status_code == 200
    responsed_topicstatuses = response.json()
    assert responsed_topicstatuses["pteam_id"] == str(pteam_id)
    assert responsed_topicstatuses["service_id"] == str(service_id)
    assert responsed_topicstatuses["topic_id"] == str(threat.topic_id)
    assert responsed_topicstatuses["tag_id"] == str(tag_id)
    assert responsed_topicstatuses["user_id"] is not None
    assert responsed_topicstatuses["topic_status"] == set_request["topic_status"]
    assert responsed_topicstatuses["note"] == set_request["note"]


def test_post_service_topic_status(testdb: Session):
    threat = threat_utils.create_threat(testdb, USER1, PTEAM1, TOPIC1, ACTION1)
    dependency = (
        testdb.query(models.Dependency)
        .filter(
            models.Dependency.dependency_id == str(threat.dependency_id),
        )
        .one()
    )
    pteam_id = dependency.service.pteam.pteam_id
    service_id = UUID(dependency.service.service_id)
    tag_id = UUID(dependency.tag.tag_id)

    set_request = {
        "topic_status": models.TopicStatusType.acknowledged,
        "logging_ids": [],
        "assignees": [],
        "note": f"acknowledged by {USER1['email']}",
        "scheduled_at": None,
    }

    response = client.post(
        f"/pteams/{pteam_id}/services/{service_id}/topicstatus/{threat.topic_id}/{tag_id}",
        headers=headers(USER1),
        json=set_request,
    )
    assert response.status_code == 200
    responsed_topicstatuses = response.json()
    assert responsed_topicstatuses["pteam_id"] == str(pteam_id)
    assert responsed_topicstatuses["service_id"] == str(service_id)
    assert responsed_topicstatuses["topic_id"] == str(threat.topic_id)
    assert responsed_topicstatuses["tag_id"] == str(tag_id)
    assert responsed_topicstatuses["user_id"] is not None
    assert responsed_topicstatuses["topic_status"] == set_request["topic_status"]
    assert responsed_topicstatuses["note"] == set_request["note"]


class TestGetPTeamServiceTagsSummary:
    @staticmethod
    def _get_access_token(user: dict) -> str:
        body = {
            "username": user["email"],
            "password": user["pass"],
        }
        response = client.post("/auth/token", data=body)
        if response.status_code != 200:
            raise HTTPError(response)
        data = response.json()
        return data["access_token"]

    @staticmethod
    def _get_service_id_by_service_name(user: dict, pteam_id: UUID | str, service_name: str) -> str:
        response = client.get(f"/pteams/{pteam_id}/services", headers=headers(user))
        if response.status_code != 200:
            raise HTTPError(response)
        data = response.json()
        service = next(filter(lambda x: x["service_name"] == service_name, data))
        return service["service_id"]

    def test_returns_summary_even_if_no_topics(self):
        create_user(USER1)
        pteam1 = create_pteam(USER1, PTEAM1)
        tag1 = create_tag(USER1, TAG1)
        # add test_service to pteam1
        test_service = "test_service"
        test_target = "test target"
        test_version = "test version"
        refs0 = {tag1.tag_name: [(test_target, test_version)]}
        upload_pteam_tags(USER1, pteam1.pteam_id, test_service, refs0)
        service_id1 = self._get_service_id_by_service_name(USER1, pteam1.pteam_id, test_service)

        # no topics, no threats, no tickets

        # get summary
        url = f"/pteams/{pteam1.pteam_id}/services/{service_id1}/tags/summary"
        user1_access_token = self._get_access_token(USER1)
        _headers = {
            "Authorization": f"Bearer {user1_access_token}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }
        response = client.get(url, headers=_headers)
        assert response.status_code == 200

        summary = response.json()
        assert summary["threat_impact_count"] == {"1": 0, "2": 0, "3": 0, "4": 1}
        assert summary["tags"] == [
            {
                "tag_id": str(tag1.tag_id),
                "tag_name": tag1.tag_name,
                "parent_id": str(tag1.parent_id) if tag1.parent_id else None,
                "parent_name": tag1.parent_name if tag1.parent_name else None,
                "threat_impact": None,
                "updated_at": None,
                "status_count": {
                    status_type.value: 0 for status_type in list(models.TopicStatusType)
                },
            }
        ]

    def test_returns_summary_even_if_no_threats(self):
        create_user(USER1)
        pteam1 = create_pteam(USER1, PTEAM1)
        tag1 = create_tag(USER1, TAG1)
        # add test_service to pteam1
        test_service = "test_service"
        test_target = "test target"
        test_version = "test version"
        refs0 = {tag1.tag_name: [(test_target, test_version)]}
        upload_pteam_tags(USER1, pteam1.pteam_id, test_service, refs0)
        service_id1 = self._get_service_id_by_service_name(USER1, pteam1.pteam_id, test_service)
        # create topic1
        create_topic(USER1, TOPIC1)  # Tag1

        # no threats nor tickets

        # get summary
        url = f"/pteams/{pteam1.pteam_id}/services/{service_id1}/tags/summary"
        user1_access_token = self._get_access_token(USER1)
        _headers = {
            "Authorization": f"Bearer {user1_access_token}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }
        response = client.get(url, headers=_headers)
        assert response.status_code == 200

        summary = response.json()
        assert summary["threat_impact_count"] == {"1": 0, "2": 0, "3": 0, "4": 1}
        assert summary["tags"] == [
            {
                "tag_id": str(tag1.tag_id),
                "tag_name": tag1.tag_name,
                "parent_id": str(tag1.parent_id) if tag1.parent_id else None,
                "parent_name": tag1.parent_name if tag1.parent_name else None,
                "threat_impact": None,
                "updated_at": None,
                "status_count": {
                    status_type.value: 0 for status_type in list(models.TopicStatusType)
                },
            }
        ]

    def test_returns_summary_if_having_alerted_ticket(self):
        create_user(USER1)
        pteam1 = create_pteam(USER1, PTEAM1)
        tag1 = create_tag(USER1, TAG1)
        # add test_service to pteam1
        test_service = "test_service"
        test_target = "test target"
        vulnerable_version = "1.2.0"  # vulnerable
        refs0 = {tag1.tag_name: [(test_target, vulnerable_version)]}
        upload_pteam_tags(USER1, pteam1.pteam_id, test_service, refs0)
        service_id1 = self._get_service_id_by_service_name(USER1, pteam1.pteam_id, test_service)
        # add actionable topic1
        action1 = {
            "action": "action one",
            "action_type": "elimination",
            "recommended": True,
            "ext": {
                "tags": [tag1.tag_name],
                "vulnerable_versions": {
                    tag1.tag_name: ["< 1.2.3"],  # > vulnerable_version
                },
            },
        }
        topic1 = create_topic(USER1, TOPIC1, actions=[action1])  # Tag1

        # get summary
        url = f"/pteams/{pteam1.pteam_id}/services/{service_id1}/tags/summary"
        user1_access_token = self._get_access_token(USER1)
        _headers = {
            "Authorization": f"Bearer {user1_access_token}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }
        response = client.get(url, headers=_headers)
        assert response.status_code == 200

        summary = response.json()
        assert summary["threat_impact_count"] == {
            **{"1": 0, "2": 0, "3": 0, "4": 0},
            str(topic1.threat_impact): 1,
        }
        assert summary["tags"] == [
            {
                "tag_id": str(tag1.tag_id),
                "tag_name": tag1.tag_name,
                "parent_id": str(tag1.parent_id) if tag1.parent_id else None,
                "parent_name": tag1.parent_name if tag1.parent_name else None,
                "threat_impact": topic1.threat_impact,
                "updated_at": datetime.isoformat(topic1.updated_at),
                "status_count": {
                    **{status_type.value: 0 for status_type in list(models.TopicStatusType)},
                    models.TopicStatusType.alerted.value: 1,  # default status is ALERTED
                },
            }
        ]


class TestGetPTeamTagsSummary:
    @staticmethod
    def _get_access_token(user: dict) -> str:
        body = {
            "username": user["email"],
            "password": user["pass"],
        }
        response = client.post("/auth/token", data=body)
        if response.status_code != 200:
            raise HTTPError(response)
        data = response.json()
        return data["access_token"]

    @staticmethod
    def _get_service_id_by_service_name(user: dict, pteam_id: UUID | str, service_name: str) -> str:
        response = client.get(f"/pteams/{pteam_id}/services", headers=headers(user))
        if response.status_code != 200:
            raise HTTPError(response)
        data = response.json()
        service = next(filter(lambda x: x["service_name"] == service_name, data))
        return service["service_id"]

    def test_returns_summary_even_if_no_topics(self):
        create_user(USER1)
        pteam1 = create_pteam(USER1, PTEAM1)
        tag1 = create_tag(USER1, TAG1)
        # add test_service to pteam1
        test_service = "test_service"
        test_target = "test target"
        test_version = "test version"
        refs0 = {tag1.tag_name: [(test_target, test_version)]}
        upload_pteam_tags(USER1, pteam1.pteam_id, test_service, refs0)
        service_id1 = self._get_service_id_by_service_name(USER1, pteam1.pteam_id, test_service)

        # no topics, no threats, no tickets

        # get summary
        url = f"/pteams/{pteam1.pteam_id}/tags/summary"
        user1_access_token = self._get_access_token(USER1)
        _headers = {
            "Authorization": f"Bearer {user1_access_token}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }
        response = client.get(url, headers=_headers)
        assert response.status_code == 200

        summary = response.json()
        assert summary["threat_impact_count"] == {"1": 0, "2": 0, "3": 0, "4": 1}
        assert summary["tags"] == [
            {
                "tag_id": str(tag1.tag_id),
                "tag_name": tag1.tag_name,
                "parent_id": str(tag1.parent_id) if tag1.parent_id else None,
                "parent_name": tag1.parent_name if tag1.parent_name else None,
                "service_ids": [service_id1],
                "threat_impact": None,
                "updated_at": None,
                "status_count": {
                    status_type.value: 0 for status_type in list(models.TopicStatusType)
                },
            }
        ]

    def test_returns_summary_even_if_no_threats(self):
        create_user(USER1)
        pteam1 = create_pteam(USER1, PTEAM1)
        tag1 = create_tag(USER1, TAG1)
        # add test_service to pteam1
        test_service = "test_service"
        test_target = "test target"
        test_version = "test version"
        refs0 = {tag1.tag_name: [(test_target, test_version)]}
        upload_pteam_tags(USER1, pteam1.pteam_id, test_service, refs0)
        service_id1 = self._get_service_id_by_service_name(USER1, pteam1.pteam_id, test_service)
        # create topic1
        create_topic(USER1, TOPIC1)  # Tag1

        # no threats nor tickets

        # get summary
        url = f"/pteams/{pteam1.pteam_id}/tags/summary"
        user1_access_token = self._get_access_token(USER1)
        _headers = {
            "Authorization": f"Bearer {user1_access_token}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }
        response = client.get(url, headers=_headers)
        assert response.status_code == 200

        summary = response.json()
        assert summary["threat_impact_count"] == {"1": 0, "2": 0, "3": 0, "4": 1}
        assert summary["tags"] == [
            {
                "tag_id": str(tag1.tag_id),
                "tag_name": tag1.tag_name,
                "parent_id": str(tag1.parent_id) if tag1.parent_id else None,
                "parent_name": tag1.parent_name if tag1.parent_name else None,
                "service_ids": [service_id1],
                "threat_impact": None,
                "updated_at": None,
                "status_count": {
                    status_type.value: 0 for status_type in list(models.TopicStatusType)
                },
            }
        ]

    def test_returns_summary_if_having_alerted_ticket(self):
        create_user(USER1)
        pteam1 = create_pteam(USER1, PTEAM1)
        tag1 = create_tag(USER1, TAG1)
        # add test_service to pteam1
        test_service = "test_service"
        test_target = "test target"
        vulnerable_version = "1.2.0"  # vulnerable
        refs0 = {tag1.tag_name: [(test_target, vulnerable_version)]}
        upload_pteam_tags(USER1, pteam1.pteam_id, test_service, refs0)
        service_id1 = self._get_service_id_by_service_name(USER1, pteam1.pteam_id, test_service)
        # add actionable topic1
        action1 = {
            "action": "action one",
            "action_type": "elimination",
            "recommended": True,
            "ext": {
                "tags": [tag1.tag_name],
                "vulnerable_versions": {
                    tag1.tag_name: ["< 1.2.3"],  # > vulnerable_version
                },
            },
        }
        topic1 = create_topic(USER1, TOPIC1, actions=[action1])  # Tag1

        # get summary
        url = f"/pteams/{pteam1.pteam_id}/tags/summary"
        user1_access_token = self._get_access_token(USER1)
        _headers = {
            "Authorization": f"Bearer {user1_access_token}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }
        response = client.get(url, headers=_headers)
        assert response.status_code == 200

        summary = response.json()
        assert summary["threat_impact_count"] == {
            **{"1": 0, "2": 0, "3": 0, "4": 0},
            str(topic1.threat_impact): 1,
        }
        assert summary["tags"] == [
            {
                "tag_id": str(tag1.tag_id),
                "tag_name": tag1.tag_name,
                "parent_id": str(tag1.parent_id) if tag1.parent_id else None,
                "parent_name": tag1.parent_name if tag1.parent_name else None,
                "service_ids": [service_id1],
                "threat_impact": topic1.threat_impact,
                "updated_at": datetime.isoformat(topic1.updated_at),
                "status_count": {
                    **{status_type.value: 0 for status_type in list(models.TopicStatusType)},
                    models.TopicStatusType.alerted.value: 1,  # default status is ALERTED
                },
            }
        ]

    def test_returns_summary_even_if_multiple_services_are_registrered(self):
        create_user(USER1)
        pteam1 = create_pteam(USER1, PTEAM1)
        tag1 = create_tag(USER1, TAG1)
        # add test_service to pteam1
        test_service1 = "test_service1"
        test_service2 = "test_service2"
        test_target = "test target"
        vulnerable_version = "1.2.0"  # vulnerable
        refs0 = {tag1.tag_name: [(test_target, vulnerable_version)]}
        upload_pteam_tags(USER1, pteam1.pteam_id, test_service1, refs0)
        upload_pteam_tags(USER1, pteam1.pteam_id, test_service2, refs0)
        service_id1 = self._get_service_id_by_service_name(USER1, pteam1.pteam_id, test_service1)
        service_id2 = self._get_service_id_by_service_name(USER1, pteam1.pteam_id, test_service2)

        # add actionable topic1
        action1 = {
            "action": "action one",
            "action_type": "elimination",
            "recommended": True,
            "ext": {
                "tags": [tag1.tag_name],
                "vulnerable_versions": {
                    tag1.tag_name: ["< 1.2.3"],  # > vulnerable_version
                },
            },
        }
        topic1 = create_topic(USER1, TOPIC1, actions=[action1])  # Tag1

        # get summary
        url = f"/pteams/{pteam1.pteam_id}/tags/summary"
        user1_access_token = self._get_access_token(USER1)
        _headers = {
            "Authorization": f"Bearer {user1_access_token}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }
        response = client.get(url, headers=_headers)
        assert response.status_code == 200

        summary = response.json()
        assert summary["threat_impact_count"] == {
            **{"1": 0, "2": 0, "3": 0, "4": 0},
            str(topic1.threat_impact): 1,
        }

        assert len(summary["tags"][0]["service_ids"]) == 2
        assert set(summary["tags"][0]["service_ids"]) == {service_id1, service_id2}

        del summary["tags"][0]["service_ids"]
        assert summary["tags"] == [
            {
                "tag_id": str(tag1.tag_id),
                "tag_name": tag1.tag_name,
                "parent_id": str(tag1.parent_id) if tag1.parent_id else None,
                "parent_name": tag1.parent_name if tag1.parent_name else None,
                "threat_impact": topic1.threat_impact,
                "updated_at": datetime.isoformat(topic1.updated_at),
                "status_count": {
                    **{status_type.value: 0 for status_type in list(models.TopicStatusType)},
                    models.TopicStatusType.alerted.value: 2,  # default status is ALERTED
                },
            }
        ]


class TestTicketStatus:

    class Common:
        @pytest.fixture(scope="function", autouse=True)
        def common_setup(self):
            self.user1 = create_user(USER1)
            self.user2 = create_user(USER2)
            self.pteam1 = create_pteam(USER1, PTEAM1)
            invitation1 = invite_to_pteam(USER1, self.pteam1.pteam_id)
            accept_pteam_invitation(USER2, invitation1.invitation_id)

            self.tag1 = create_tag(USER1, TAG1)
            # add test_service to pteam1
            test_service = "test_service"
            test_target = "test target"
            test_version = "1.2.3"
            refs0 = {self.tag1.tag_name: [(test_target, test_version)]}
            upload_pteam_tags(USER1, self.pteam1.pteam_id, test_service, refs0)
            self.service_id1 = self._get_service_id_by_service_name(
                USER1, self.pteam1.pteam_id, test_service
            )

        @pytest.fixture(scope="function", autouse=False)
        def actionable_topic1(self):
            action1 = self._gen_action([self.tag1.tag_name])
            self.topic1 = create_topic(
                USER1, {**TOPIC1, "tags": [self.tag1.tag_name], "actions": [action1]}
            )
            tickets = self._get_tickets(
                self.pteam1.pteam_id, self.service_id1, self.topic1.topic_id, self.tag1.tag_id
            )
            self.ticket_id1 = tickets[0]["ticket_id"]

        @pytest.fixture(scope="function", autouse=False)
        def not_actionable_topic1(self):
            self.topic1 = create_topic(
                USER1, {**TOPIC1, "tags": [self.tag1.tag_name], "actions": []}
            )
            self.ticket_id1 = None

        @staticmethod
        def _get_access_token(user: dict) -> str:
            body = {
                "username": user["email"],
                "password": user["pass"],
            }
            response = client.post("/auth/token", data=body)
            if response.status_code != 200:
                raise HTTPError(response)
            data = response.json()
            return data["access_token"]

        @staticmethod
        def _get_service_id_by_service_name(
            user: dict, pteam_id: UUID | str, service_name: str
        ) -> str:
            response = client.get(f"/pteams/{pteam_id}/services", headers=headers(user))
            if response.status_code != 200:
                raise HTTPError(response)
            data = response.json()
            service = next(filter(lambda x: x["service_name"] == service_name, data))
            return service["service_id"]

        @staticmethod
        def _gen_action(tag_names: list[str]) -> dict:
            return {
                "action": f"sample action for {str(tag_names)}",
                "action_type": models.ActionType.elimination,
                "recommended": True,
                "ext": {
                    "tags": tag_names,
                    "vulnerable_versions": {tag_name: ["<999.99.9"] for tag_name in tag_names},
                },
            }

        def _get_tickets(self, pteam_id: str, service_id: str, topic_id: str, tag_id: str) -> dict:
            url = (
                f"/pteams/{pteam_id}/services/{service_id}"
                f"/topics/{topic_id}/tags/{tag_id}/tickets"
            )
            user1_access_token = self._get_access_token(USER1)
            _headers = {
                "Authorization": f"Bearer {user1_access_token}",
                "Content-Type": "application/json",
                "accept": "application/json",
            }
            return client.get(url, headers=_headers).json()

        def _set_ticket_status(
            self, pteam_id: str, service_id: str, ticket_id: str, request: dict
        ) -> dict:
            url = f"/pteams/{pteam_id}/services/{service_id}/ticketstatus/{ticket_id}"
            user1_access_token = self._get_access_token(USER1)
            _headers = {
                "Authorization": f"Bearer {user1_access_token}",
                "Content-Type": "application/json",
                "accept": "application/json",
            }
            return client.post(url, headers=_headers, json=request).json()

        def _get_ticket_status(self, pteam_id: str, service_id: str, ticket_id: str) -> dict:
            url = f"/pteams/{pteam_id}/services/{service_id}/ticketstatus/{ticket_id}"
            user1_access_token = self._get_access_token(USER1)
            _headers = {
                "Authorization": f"Bearer {user1_access_token}",
                "Content-Type": "application/json",
                "accept": "application/json",
            }
            return client.get(url, headers=_headers).json()

    class TestGet(Common):

        def test_returns_initial_status_if_no_status_created(self, actionable_topic1):
            url = (
                f"/pteams/{self.pteam1.pteam_id}/services/{self.service_id1}"
                f"/ticketstatus/{self.ticket_id1}"
            )
            user1_access_token = self._get_access_token(USER1)
            _headers = {
                "Authorization": f"Bearer {user1_access_token}",
                "Content-Type": "application/json",
                "accept": "application/json",
            }
            response = client.get(url, headers=_headers)
            assert response.status_code == 200

            data = response.json()
            expected_status = {
                "status_id": None,
                "ticket_id": str(self.ticket_id1),
                "topic_status": models.TopicStatusType.alerted.value,
                "user_id": None,
                "created_at": None,
                "assignees": [],
                "note": None,
                "scheduled_at": None,
                "action_logs": [],
            }
            assert data == expected_status

        def test_returns_current_status_if_status_created(self, actionable_topic1):
            status_request = {
                "topic_status": models.TopicStatusType.scheduled.value,
                "assignees": [str(self.user2.user_id)],
                "note": "assign user2 and schedule at 2345/6/7",
                "scheduled_at": "2345-06-07T08:09:10",
            }
            set_response = self._set_ticket_status(
                self.pteam1.pteam_id, self.service_id1, self.ticket_id1, status_request
            )

            # get ticket status
            url = (
                f"/pteams/{self.pteam1.pteam_id}/services/{self.service_id1}"
                f"/ticketstatus/{self.ticket_id1}"
            )
            user1_access_token = self._get_access_token(USER1)
            _headers = {
                "Authorization": f"Bearer {user1_access_token}",
                "Content-Type": "application/json",
                "accept": "application/json",
            }
            response = client.get(url, headers=_headers)
            assert response.status_code == 200

            data = response.json()
            expected_status = {
                "status_id": set_response["status_id"],
                "ticket_id": str(self.ticket_id1),
                "user_id": str(self.user1.user_id),
                "created_at": set_response["created_at"],
                "action_logs": [],
                **status_request,
            }
            assert data == expected_status

    class TestSet(Common):

        def test_set_requested_status(self, actionable_topic1):
            status_request = {
                "topic_status": models.TopicStatusType.scheduled.value,
                "assignees": [str(self.user2.user_id)],
                "note": "assign user2 and schedule at 2345/6/7",
                "scheduled_at": "2345-06-07T08:09:10",
            }
            url = (
                f"/pteams/{self.pteam1.pteam_id}/services/{self.service_id1}"
                f"/ticketstatus/{self.ticket_id1}"
            )
            user1_access_token = self._get_access_token(USER1)
            _headers = {
                "Authorization": f"Bearer {user1_access_token}",
                "Content-Type": "application/json",
                "accept": "application/json",
            }
            response = client.post(url, headers=_headers, json=status_request)
            assert response.status_code == 200

            data = response.json()
            # check not-none only because we do not have values to compare
            for key in {"status_id", "created_at"}:
                assert data[key] is not None
                del data[key]
            expected_status = {
                "ticket_id": str(self.ticket_id1),
                "user_id": str(self.user1.user_id),
                "action_logs": [],
                **status_request,
            }
            assert data == expected_status

        def test_it_should_return_400_when_topic_status_is_scheduled_and_there_is_no_schduled_at(
            self, actionable_topic1
        ):
            status_request = {
                "topic_status": models.TopicStatusType.scheduled.value,
                "assignees": [str(self.user2.user_id)],
                "note": "assign user2 and schedule at 2345/6/7",
            }
            url = (
                f"/pteams/{self.pteam1.pteam_id}/services/{self.service_id1}"
                f"/ticketstatus/{self.ticket_id1}"
            )
            user1_access_token = self._get_access_token(USER1)
            _headers = {
                "Authorization": f"Bearer {user1_access_token}",
                "Content-Type": "application/json",
                "accept": "application/json",
            }
            response = client.post(url, headers=_headers, json=status_request)
            assert response.status_code == 400

            set_response = response.json()
            assert set_response["detail"] == "If statsu is schduled, specify schduled_at"

        def test_it_should_put_None_in_schduled_at_when_schduled_at_is_datetime_fromtimestamp_zero(
            self, actionable_topic1
        ):
            status_request = {
                "topic_status": models.TopicStatusType.scheduled.value,
                "assignees": [str(self.user2.user_id)],
                "note": "assign user2 and schedule at 2345/6/7",
                "scheduled_at": str(datetime.fromtimestamp(0)),
            }
            url = (
                f"/pteams/{self.pteam1.pteam_id}/services/{self.service_id1}"
                f"/ticketstatus/{self.ticket_id1}"
            )
            user1_access_token = self._get_access_token(USER1)
            _headers = {
                "Authorization": f"Bearer {user1_access_token}",
                "Content-Type": "application/json",
                "accept": "application/json",
            }
            response = client.post(url, headers=_headers, json=status_request)
            if response.status_code != 200:
                raise HTTPError(response)

            data = response.json()
            assert data["scheduled_at"] is None

            # verification of correct registration in DB
            get_response = self._get_ticket_status(
                self.pteam1.pteam_id, self.service_id1, self.ticket_id1
            )

            assert get_response["scheduled_at"] is None


class TestGetTickets:

    @pytest.fixture(scope="function", autouse=True)
    def common_setup(self):
        self.user1 = create_user(USER1)
        self.user2 = create_user(USER2)
        self.pteam1 = create_pteam(USER1, PTEAM1)
        invitation1 = invite_to_pteam(USER1, self.pteam1.pteam_id)
        accept_pteam_invitation(USER2, invitation1.invitation_id)

        self.tag1 = create_tag(USER1, TAG1)
        # add test_service to pteam1
        test_service = "test_service"
        test_target = "test target"
        test_version = "1.2.3"
        refs0 = {self.tag1.tag_name: [(test_target, test_version)]}
        upload_pteam_tags(USER1, self.pteam1.pteam_id, test_service, refs0)
        self.service_id1 = self._get_service_id_by_service_name(
            USER1, self.pteam1.pteam_id, test_service
        )

    @pytest.fixture(scope="function", autouse=False)
    def actionable_topic1(self):
        action1 = self._gen_action([self.tag1.tag_name])
        self.topic1 = create_topic(
            USER1, {**TOPIC1, "tags": [self.tag1.tag_name], "actions": [action1]}
        )

    @pytest.fixture(scope="function", autouse=False)
    def not_actionable_topic1(self):
        self.topic1 = create_topic(USER1, {**TOPIC1, "tags": [self.tag1.tag_name], "actions": []})

    @staticmethod
    def _get_access_token(user: dict) -> str:
        body = {
            "username": user["email"],
            "password": user["pass"],
        }
        response = client.post("/auth/token", data=body)
        if response.status_code != 200:
            raise HTTPError(response)
        data = response.json()
        return data["access_token"]

    @staticmethod
    def _get_service_id_by_service_name(user: dict, pteam_id: UUID | str, service_name: str) -> str:
        response = client.get(f"/pteams/{pteam_id}/services", headers=headers(user))
        if response.status_code != 200:
            raise HTTPError(response)
        data = response.json()
        service = next(filter(lambda x: x["service_name"] == service_name, data))
        return service["service_id"]

    @staticmethod
    def _gen_action(tag_names: list[str]) -> dict:
        return {
            "action": f"sample action for {str(tag_names)}",
            "action_type": models.ActionType.elimination,
            "recommended": True,
            "ext": {
                "tags": tag_names,
                "vulnerable_versions": {tag_name: ["<999.99.9"] for tag_name in tag_names},
            },
        }

    def _set_ticket_status(
        self, pteam_id: str, service_id: str, ticket_id: str, request: dict
    ) -> dict:
        url = f"/pteams/{pteam_id}/services/{service_id}/ticketstatus/{ticket_id}"
        user1_access_token = self._get_access_token(USER1)
        _headers = {
            "Authorization": f"Bearer {user1_access_token}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }
        return client.post(url, headers=_headers, json=request).json()

    def test_returns_empty_if_no_tickets(self, not_actionable_topic1):
        url = (
            f"/pteams/{self.pteam1.pteam_id}/services/{self.service_id1}"
            f"/topics/{self.topic1.topic_id}/tags/{self.tag1.tag_id}/tickets"
        )
        user1_access_token = self._get_access_token(USER1)
        _headers = {
            "Authorization": f"Bearer {user1_access_token}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }
        response = client.get(url, headers=_headers)
        assert response.status_code == 200
        assert response.json() == []

    def test_returns_ticket_with_initial_status_if_no_status_created(
        self, testdb, actionable_topic1
    ):
        db_dependency1 = testdb.scalars(select(models.Dependency)).one()
        db_threat1 = testdb.scalars(select(models.Threat)).one()
        db_ticket1 = testdb.scalars(select(models.Ticket)).one()
        expected_ticket_response1 = {
            "ticket_id": str(db_ticket1.ticket_id),
            "threat_id": str(db_threat1.threat_id),
            "created_at": datetime.isoformat(db_ticket1.created_at),
            "updated_at": datetime.isoformat(db_ticket1.updated_at),
            "ssvc_deployer_priority": (
                None
                if db_ticket1.ssvc_deployer_priority is None
                else db_ticket1.ssvc_deployer_priority.value
            ),
            "threat": {
                "threat_id": str(db_threat1.threat_id),
                "topic_id": str(self.topic1.topic_id),
                "dependency_id": str(db_dependency1.dependency_id),
            },
            "current_ticket_status": {
                "status_id": None,
                "ticket_id": str(db_ticket1.ticket_id),
                "topic_status": models.TopicStatusType.alerted.value,
                "user_id": None,
                "created_at": None,
                "assignees": [],
                "note": None,
                "scheduled_at": None,
                "action_logs": [],
            },
        }

        url = (
            f"/pteams/{self.pteam1.pteam_id}/services/{self.service_id1}"
            f"/topics/{self.topic1.topic_id}/tags/{self.tag1.tag_id}/tickets"
        )
        user1_access_token = self._get_access_token(USER1)
        _headers = {
            "Authorization": f"Bearer {user1_access_token}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }
        response = client.get(url, headers=_headers)
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        ticket1 = data[0]
        assert ticket1 == expected_ticket_response1

    def test_returns_ticket_with_current_status_if_status_created(self, testdb, actionable_topic1):
        db_dependency1 = testdb.scalars(select(models.Dependency)).one()
        db_threat1 = testdb.scalars(select(models.Threat)).one()
        db_ticket1 = testdb.scalars(select(models.Ticket)).one()
        status_request = {
            "topic_status": models.TopicStatusType.scheduled.value,
            "assignees": [str(self.user2.user_id)],
            "note": "assign user2 and schedule at 2345/6/7",
            "scheduled_at": "2345-06-07T08:09:10",
        }
        self._set_ticket_status(
            self.pteam1.pteam_id, self.service_id1, db_ticket1.ticket_id, status_request
        )

        db_ticket_status1 = testdb.scalars(select(models.TicketStatus)).one()
        expected_ticket_response1 = {
            "ticket_id": str(db_ticket1.ticket_id),
            "threat_id": str(db_threat1.threat_id),
            "created_at": datetime.isoformat(db_ticket1.created_at),
            "updated_at": datetime.isoformat(db_ticket1.updated_at),
            "ssvc_deployer_priority": (
                None
                if db_ticket1.ssvc_deployer_priority is None
                else db_ticket1.ssvc_deployer_priority.value
            ),
            "threat": {
                "threat_id": str(db_threat1.threat_id),
                "topic_id": str(self.topic1.topic_id),
                "dependency_id": str(db_dependency1.dependency_id),
            },
            "current_ticket_status": {
                "status_id": str(db_ticket_status1.status_id),
                "ticket_id": str(db_ticket1.ticket_id),
                "user_id": str(self.user1.user_id),
                "created_at": datetime.isoformat(db_ticket_status1.created_at),
                "action_logs": [],
                **status_request,
            },
        }

        url = (
            f"/pteams/{self.pteam1.pteam_id}/services/{self.service_id1}"
            f"/topics/{self.topic1.topic_id}/tags/{self.tag1.tag_id}/tickets"
        )
        user1_access_token = self._get_access_token(USER1)
        _headers = {
            "Authorization": f"Bearer {user1_access_token}",
            "Content-Type": "application/json",
            "accept": "application/json",
        }
        response = client.get(url, headers=_headers)
        assert response.status_code == 200

        data = response.json()
        assert len(data) == 1
        ticket1 = data[0]
        assert ticket1 == expected_ticket_response1
