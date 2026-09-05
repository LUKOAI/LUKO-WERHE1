"""Placement simulation through SP-API Fulfillment Inbound v2024-03-20.

Flow (all operations documented in the official model, see
docs/AMAZON_ZASADY.md §6):

1. ``POST /inbound/fba/2024-03-20/inboundPlans`` (createInboundPlan) with
   destinationMarketplaces=[marketplace], sourceAddress, items=[{msku, quantity,
   prepOwner, labelOwner}] -> operationId, inboundPlanId
2. ``POST .../inboundPlans/{id}/packingOptions`` (generatePackingOptions), then
   ``GET .../packingOptions`` and ``POST .../packingOptions/{pid}/confirmation``
3. ``POST .../inboundPlans/{id}/items/packingInformation`` (setPackingInformation)
   with boxes per packing group (dimensions CM, weight KG, contents)
4. ``POST .../inboundPlans/{id}/placementOptions`` (generatePlacementOptions),
   ``GET .../placementOptions`` -> each option lists shipmentIds; ``GET
   .../shipments/{shipmentId}`` gives destination.warehouseId (e.g. WRO5/XPO1)
   and ``GET .../shipments/{shipmentId}/boxes`` the boxes routed there.
5. Nothing is confirmed: the inbound plan stays a draft (it can be cancelled
   with ``PUT .../inboundPlans/{id}/cancellation``). Rate limits: 2 rps.

Long-running operations return an operationId; poll
``GET /inbound/fba/2024-03-20/operations/{operationId}`` until SUCCESS.

Authentication: LWA refresh token -> access token (``https://api.amazon.com/auth/o2/token``),
header ``x-amz-access-token``. EU endpoint ``https://sellingpartnerapi-eu.amazon.com``.
Marketplace ids: DE A1PA6795UKMFR9, PL A1C3SOZRARQ6R3.

This module implements the HTTP plumbing with the standard library only and a
``simulate_placement`` helper that returns a {msku: warehouseId} verdict. It is
not exercised by tests (needs real credentials); treat it as a starting point.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Optional

EU_ENDPOINT = "https://sellingpartnerapi-eu.amazon.com"
LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
API = "/inbound/fba/2024-03-20"
MARKETPLACES = {"DE": "A1PA6795UKMFR9", "PL": "A1C3SOZRARQ6R3", "FR": "A13V1IB3VIYZZH", "IT": "APJ6JRA9NG5V4", "ES": "A1RKKUPIHCS9HS", "UK": "A1F83G8C2ARO7P"}


@dataclass
class SpApiConfig:
    client_id: str
    client_secret: str
    refresh_token: str
    marketplace_id: str = MARKETPLACES["DE"]
    endpoint: str = EU_ENDPOINT
    source_address: dict = field(default_factory=dict)  # name, addressLine1, city, postalCode, countryCode, phoneNumber

    @classmethod
    def from_env(cls) -> Optional["SpApiConfig"]:
        cid, sec, rt = os.environ.get("SPAPI_CLIENT_ID"), os.environ.get("SPAPI_CLIENT_SECRET"), os.environ.get("SPAPI_REFRESH_TOKEN")
        if not (cid and sec and rt):
            return None
        addr = json.loads(os.environ.get("SPAPI_SOURCE_ADDRESS", "{}") or "{}")
        return cls(cid, sec, rt, os.environ.get("SPAPI_MARKETPLACE_ID", MARKETPLACES["DE"]), os.environ.get("SPAPI_ENDPOINT", EU_ENDPOINT), addr)


class SpApiError(RuntimeError):
    pass


class InboundClient:
    def __init__(self, cfg: SpApiConfig):
        self.cfg = cfg
        self._token: Optional[str] = None
        self._token_exp = 0.0

    # -- auth ---------------------------------------------------------------- #
    def access_token(self) -> str:
        if self._token and time.time() < self._token_exp - 60:
            return self._token
        body = urllib.parse.urlencode({"grant_type": "refresh_token", "refresh_token": self.cfg.refresh_token,
                                       "client_id": self.cfg.client_id, "client_secret": self.cfg.client_secret}).encode()
        req = urllib.request.Request(LWA_TOKEN_URL, data=body, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=30) as r:
            d = json.load(r)
        self._token = d["access_token"]
        self._token_exp = time.time() + int(d.get("expires_in", 3600))
        return self._token

    def _call(self, method: str, path: str, body: Optional[dict] = None, query: Optional[dict] = None) -> dict:
        url = self.cfg.endpoint + path + (("?" + urllib.parse.urlencode(query)) if query else "")
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"x-amz-access-token": self.access_token(), "Content-Type": "application/json", "Accept": "application/json"})
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    txt = r.read().decode()
                    return json.loads(txt) if txt else {}
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 4:
                    time.sleep(1.0 + attempt)
                    continue
                raise SpApiError(f"{method} {path}: HTTP {e.code} {e.read().decode()[:500]}") from e
        raise SpApiError("rate limited")

    def wait(self, operation_id: str, timeout_s: float = 120) -> dict:
        t0 = time.time()
        while True:
            op = self._call("GET", f"{API}/operations/{operation_id}")
            st = op.get("operationStatus")
            if st == "SUCCESS":
                return op
            if st == "FAILED":
                raise SpApiError(f"operation {operation_id} failed: {op.get('operationProblems')}")
            if time.time() - t0 > timeout_s:
                raise SpApiError(f"operation {operation_id} timed out")
            time.sleep(2.0)

    # -- inbound plan --------------------------------------------------------- #
    def create_plan(self, name: str, items: list[dict]) -> str:
        body = {"name": name[:40], "destinationMarketplaces": [self.cfg.marketplace_id], "sourceAddress": self.cfg.source_address,
                "items": [{"msku": i["msku"], "quantity": int(i["quantity"]), "prepOwner": i.get("prepOwner", "SELLER"), "labelOwner": i.get("labelOwner", "SELLER")} for i in items]}
        r = self._call("POST", f"{API}/inboundPlans", body)
        self.wait(r["operationId"])
        return r["inboundPlanId"]

    def packing_options(self, plan_id: str) -> list[dict]:
        r = self._call("POST", f"{API}/inboundPlans/{plan_id}/packingOptions")
        self.wait(r["operationId"])
        return self._call("GET", f"{API}/inboundPlans/{plan_id}/packingOptions").get("packingOptions", [])

    def confirm_packing_option(self, plan_id: str, option_id: str) -> None:
        r = self._call("POST", f"{API}/inboundPlans/{plan_id}/packingOptions/{option_id}/confirmation")
        self.wait(r["operationId"])

    def set_packing_information(self, plan_id: str, package_groupings: list[dict]) -> None:
        r = self._call("POST", f"{API}/inboundPlans/{plan_id}/items/packingInformation", {"packageGroupings": package_groupings})
        self.wait(r["operationId"])

    def placement_options(self, plan_id: str) -> list[dict]:
        r = self._call("POST", f"{API}/inboundPlans/{plan_id}/placementOptions")
        self.wait(r["operationId"])
        return self._call("GET", f"{API}/inboundPlans/{plan_id}/placementOptions").get("placementOptions", [])

    def shipment(self, plan_id: str, shipment_id: str) -> dict:
        return self._call("GET", f"{API}/inboundPlans/{plan_id}/shipments/{shipment_id}")

    def shipment_items(self, plan_id: str, shipment_id: str) -> list[dict]:
        out, token = [], None
        while True:
            q = {"pageSize": 1000}
            if token:
                q["paginationToken"] = token
            r = self._call("GET", f"{API}/inboundPlans/{plan_id}/shipments/{shipment_id}/items", query=q)
            out += r.get("items", [])
            token = (r.get("pagination") or {}).get("nextToken")
            if not token:
                return out

    def cancel_plan(self, plan_id: str) -> None:
        r = self._call("PUT", f"{API}/inboundPlans/{plan_id}/cancellation")
        self.wait(r["operationId"])


def box_input(sku_units: dict[str, int], length_cm: float, width_cm: float, height_cm: float, weight_kg: float, quantity: int = 1) -> dict:
    return {"dimensions": {"length": length_cm, "width": width_cm, "height": height_cm, "unitOfMeasurement": "CM"},
            "weight": {"value": weight_kg, "unit": "KG"}, "quantity": quantity, "contentInformationSource": "BOX_CONTENT_PROVIDED",
            "items": [{"msku": m, "quantity": q, "prepOwner": "SELLER", "labelOwner": "SELLER"} for m, q in sku_units.items()]}


def simulate_placement(client: InboundClient, name: str, items: list[dict], boxes: Optional[list[dict]] = None, cancel: bool = True) -> dict[str, Any]:
    """Create a draft inbound plan, read Amazon's placement options, return
    {"plan_id", "options": [{"id", "shipments": [{"id", "fc", "items": {msku: qty}}], "fees"}]} and cancel the draft."""
    plan_id = client.create_plan(name, items)
    try:
        packs = client.packing_options(plan_id)
        if packs:
            client.confirm_packing_option(plan_id, packs[0]["packingOptionId"])
            if boxes:
                groups = [{"packingGroupId": g, "boxes": boxes} for g in packs[0].get("packingGroups", [])]
                client.set_packing_information(plan_id, groups)
        options = []
        for opt in client.placement_options(plan_id):
            shipments = []
            for sid in opt.get("shipmentIds", []):
                sh = client.shipment(plan_id, sid)
                fc = ((sh.get("destination") or {}).get("warehouseId")) or ""
                items_ = {i["msku"]: int(i.get("quantity", 0)) for i in client.shipment_items(plan_id, sid)}
                shipments.append({"id": sid, "fc": fc, "items": items_})
            options.append({"id": opt.get("placementOptionId"), "status": opt.get("status"), "shipments": shipments,
                            "fees": opt.get("fees", []), "discounts": opt.get("discounts", [])})
        return {"plan_id": plan_id, "options": options}
    finally:
        if cancel:
            try:
                client.cancel_plan(plan_id)
            except SpApiError:
                pass


def verdict_from_options(result: dict) -> dict[str, str]:
    """msku -> FC from the first (recommended) placement option."""
    out: dict[str, str] = {}
    opts = result.get("options") or []
    if not opts:
        return out
    for sh in opts[0]["shipments"]:
        for msku in sh["items"]:
            out[msku] = sh["fc"]
    return out
