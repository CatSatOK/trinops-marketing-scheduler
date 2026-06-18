"""GDPR: consent capture on the lead webhook + right-to-erasure delete."""


def test_consent_flag_captured_when_truthy(client):
    resp = client.post("/leads/webhook", json={"name": "Ada", "consent": "yes"})
    assert resp.status_code == 201
    assert resp.json()["consent"] is True


def test_consent_defaults_false_when_absent(client):
    resp = client.post("/leads/webhook", json={"name": "Ada"})
    assert resp.status_code == 201
    assert resp.json()["consent"] is False


def test_erase_lead_removes_it(client):
    created = client.post("/leads/webhook", json={"name": "Forget", "email": "f@x.test"})
    lead_id = created.json()["id"]

    assert client.delete(f"/leads/{lead_id}").status_code == 204
    # gone from the inbox and individually 404
    assert all(l["id"] != lead_id for l in client.get("/leads").json())


def test_erase_missing_lead_404(client):
    assert client.delete("/leads/999999").status_code == 404
