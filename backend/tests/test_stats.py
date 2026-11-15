from httpx import AsyncClient

from tests.helpers import signup
from tests.test_booking import book, setup_clinic, slots


async def test_stats_counts_noshow_rate_and_doctor_load(client: AsyncClient) -> None:
    c = await setup_clinic(client)
    h = c["o"]["h"]
    sl = await slots(client, c)
    ids = []
    for i in range(4):
        r = await book(client, c, sl[i], f"+99890111000{i}")
        ids.append(r.json()["appointment"]["id"])
    await client.patch(f"/appointments/{ids[0]}/status", headers=h, json={"status": "completed"})
    await client.patch(f"/appointments/{ids[1]}/status", headers=h, json={"status": "no_show"})
    await client.patch(f"/appointments/{ids[2]}/status", headers=h, json={"status": "cancelled"})
    r = await client.get("/stats", headers=h, params={"date_from": "2030-03-01", "date_to": "2030-03-31"})
    body = r.json()
    assert r.status_code == 200
    assert body["total"] == 3  # cancelled excluded
    assert body["per_day"] == [{"date": "2030-03-04", "count": 3}]
    assert body["no_show_rate"] == 0.5
    assert body["busiest_doctors"][0]["appointments"] == 3
    other = await signup(client, "o")
    empty = (await client.get("/stats", headers=other["h"])).json()
    assert empty["total"] == 0 and empty["no_show_rate"] is None and empty["busiest_doctors"] == []
