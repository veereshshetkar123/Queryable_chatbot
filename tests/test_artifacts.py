"""Saved artifacts: the Artifacts library in the sidebar."""

import pytest

from backend import artifacts

QUERY = {"collection": "span_companies", "operation": "count", "filters": {"country": "India"}}
VISUAL = {"title": "Companies by country", "stats": [], "charts": [{"kind": "bar"}], "insights": []}
GEO = {"places": [{"key": "IN", "name": "India", "value": 2}], "regions": [], "continents": ["Asia"], "insights": []}


@pytest.fixture()
def library(logged_in):
    artifacts.ensure_indexes()
    artifacts.artifacts.delete_many({})
    yield logged_in
    artifacts.artifacts.delete_many({})


def save(question, calls, username="tester", thread_id="t-1"):
    return artifacts.save_run_artifacts(username, thread_id, question, calls)


def test_build_maps_tools_to_types_and_skips_the_rest():
    docs = artifacts.build_artifacts("tester", "t-1", "  How many   in India? ", [
        ("route_question", {}, {"route": "database_query"}),
        ("query_mongodb", QUERY, {"ok": True, "rows_returned": 1, "preview": [{"count": 2}]}),
        ("query_mongodb", QUERY, {"ok": False, "error": "rejected"}),
        ("visual_analysis", {"question": "q"}, VISUAL),
        ("geo_map", {"question": "q"}, GEO),
    ])
    assert [doc["type"] for doc in docs] == ["qc_mongodb_query", "qc_visual_analysis", "qc_geo_map"]
    assert all(doc["title"] == "How many in India?" for doc in docs)
    # The query renderer needs the executed query, which lives in content.
    assert docs[0]["content"]["query"] == QUERY
    assert docs[1]["content"] == VISUAL


def test_list_search_filter_and_get(library):
    save("Companies in India", [("visual_analysis", {}, VISUAL), ("geo_map", {}, GEO)])
    save("Attrition by department", [("visual_analysis", {}, VISUAL)])

    listed = library.get("/api/artifacts").json()["artifacts"]
    assert len(listed) == 3
    assert "content" not in listed[0]
    assert set(listed[0]) == {"id", "title", "type", "threadId", "updatedAt"}

    found = library.get("/api/artifacts", params={"name": "india"}).json()["artifacts"]
    assert {item["type"] for item in found} == {"qc_visual_analysis", "qc_geo_map"}

    maps = library.get("/api/artifacts", params={"type": "qc_geo_map"}).json()["artifacts"]
    assert [item["type"] for item in maps] == ["qc_geo_map"]

    full = library.get(f"/api/artifacts/{maps[0]['id']}").json()
    assert full["content"] == GEO
    assert full["threadId"] == "t-1"


def test_pagination(library):
    for index in range(5):
        save(f"Question {index}", [("visual_analysis", {}, VISUAL)])
    first = library.get("/api/artifacts", params={"limit": 3}).json()
    assert len(first["artifacts"]) == 3 and first["nextCursor"]
    second = library.get("/api/artifacts", params={"limit": 3, "cursor": first["nextCursor"]}).json()
    assert len(second["artifacts"]) == 2 and "nextCursor" not in second
    ids = [a["id"] for a in first["artifacts"] + second["artifacts"]]
    assert len(set(ids)) == 5


def test_rename_and_delete(library):
    save("Original", [("visual_analysis", {}, VISUAL)])
    item = library.get("/api/artifacts").json()["artifacts"][0]

    renamed = library.patch(f"/api/artifacts/{item['id']}", json={"title": "  Board   chart "}).json()
    assert renamed["title"] == "Board chart"

    assert library.delete(f"/api/artifacts/{item['id']}").status_code == 200
    assert library.get(f"/api/artifacts/{item['id']}").status_code == 404


def test_other_users_artifacts_are_invisible(library):
    save("Someone else's", [("visual_analysis", {}, VISUAL)], username="someone-else")
    other = artifacts.artifacts.find_one({"username": "someone-else"})
    assert library.get("/api/artifacts").json()["artifacts"] == []
    assert library.get(f"/api/artifacts/{other['_id']}").status_code == 404
    assert library.delete(f"/api/artifacts/{other['_id']}").status_code == 404


def test_deleting_a_conversation_deletes_its_artifacts(library):
    thread = library.post("/api/threads/create", json={"messages": []}).json()
    save("In a thread", [("visual_analysis", {}, VISUAL)], thread_id=thread["id"])
    assert len(library.get("/api/artifacts").json()["artifacts"]) == 1
    library.delete(f"/api/threads/delete/{thread['id']}")
    assert library.get("/api/artifacts").json()["artifacts"] == []


def test_requires_login(app_client):
    assert app_client.get("/api/artifacts").status_code == 401
