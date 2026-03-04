from __future__ import annotations

import xmlrpc.client
from abc import ABC, abstractmethod

import httpx


class AdapterError(Exception):
    pass


class ConnectorAdapter(ABC):
    name: str

    @abstractmethod
    def pull_products(self, since_cursor: str = "") -> dict:
        raise NotImplementedError

    @abstractmethod
    def push_product(self, payload: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def pull_orders(self, since_cursor: str = "") -> dict:
        raise NotImplementedError

    @abstractmethod
    def ack_fulfillment(self, order_id: str, tracking: dict) -> dict:
        raise NotImplementedError

    @abstractmethod
    def pull_refunds(self, since_cursor: str = "") -> dict:
        raise NotImplementedError

    @abstractmethod
    def rate_limit_strategy(self) -> dict:
        raise NotImplementedError

    @abstractmethod
    def pull_inbound_emails(
        self,
        *,
        since_cursor: str = "",
        target_address: str = "",
        source: str = "odoo_alias_fetchmail",
        limit: int = 200,
    ) -> dict:
        raise NotImplementedError


class ShopifyAdapter(ConnectorAdapter):
    name = "shopify"

    def __init__(self, *, shop_domain: str, access_token: str, api_version: str = "2024-10"):
        self.shop_domain = shop_domain
        self.access_token = access_token
        self.api_version = api_version

    @property
    def _base_url(self) -> str:
        return f"https://{self.shop_domain}/admin/api/{self.api_version}"

    @property
    def _headers(self) -> dict:
        return {
            "X-Shopify-Access-Token": self.access_token,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _request(self, method: str, path: str, *, params: dict | None = None, payload: dict | None = None) -> dict:
        url = f"{self._base_url}{path}"
        with httpx.Client(timeout=30) as client:
            response = client.request(method, url, headers=self._headers, params=params, json=payload)
        if response.status_code >= 400:
            raise AdapterError(f"shopify api error status={response.status_code} body={response.text}")
        return response.json()

    def pull_products(self, since_cursor: str = "") -> dict:
        params = {"limit": 250}
        if since_cursor:
            params["updated_at_min"] = since_cursor
        data = self._request("GET", "/products.json", params=params)
        return {"items": data.get("products", []), "next_cursor": ""}

    def push_product(self, payload: dict) -> dict:
        # Shopify requires a wrapper key named "product" for create/update operations.
        product = payload.get("product", payload)
        if product.get("id"):
            data = self._request("PUT", f"/products/{product['id']}.json", payload={"product": product})
        else:
            data = self._request("POST", "/products.json", payload={"product": product})
        return {"product": data.get("product", {}), "status": "synced"}

    def pull_orders(self, since_cursor: str = "") -> dict:
        params = {"status": "any", "limit": 250}
        if since_cursor:
            params["updated_at_min"] = since_cursor
        data = self._request("GET", "/orders.json", params=params)
        return {"items": data.get("orders", []), "next_cursor": ""}

    def ack_fulfillment(self, order_id: str, tracking: dict) -> dict:
        payload = {
            "fulfillment": {
                "line_items_by_fulfillment_order": tracking.get("line_items_by_fulfillment_order", []),
                "tracking_info": {
                    "number": tracking.get("number", ""),
                    "company": tracking.get("company", ""),
                    "url": tracking.get("url", ""),
                },
                "notify_customer": tracking.get("notify_customer", False),
            }
        }
        data = self._request("POST", f"/orders/{order_id}/fulfillments.json", payload=payload)
        return {"status": "accepted", "fulfillment": data.get("fulfillment", {})}

    def pull_refunds(self, since_cursor: str = "") -> dict:
        orders = self.pull_orders(since_cursor=since_cursor).get("items", [])
        refunds: list[dict] = []
        for order in orders:
            order_id = order.get("id")
            if not order_id:
                continue
            data = self._request("GET", f"/orders/{order_id}/refunds.json")
            for refund in data.get("refunds", []):
                refund["order_id"] = order_id
                refunds.append(refund)
        return {"items": refunds, "next_cursor": ""}

    def rate_limit_strategy(self) -> dict:
        return {"mode": "token_bucket", "max_rps": 2, "burst": 40}

    def pull_inbound_emails(
        self,
        *,
        since_cursor: str = "",
        target_address: str = "",
        source: str = "odoo_alias_fetchmail",
        limit: int = 200,
    ) -> dict:
        return {"items": [], "next_cursor": ""}


class OdooAdapter(ConnectorAdapter):
    name = "odoo"

    def __init__(
        self,
        *,
        base_url: str,
        database: str,
        username: str,
        password: str,
        protocol: str = "jsonrpc",
    ):
        self.base_url = base_url.rstrip("/")
        self.database = database
        self.username = username
        self.password = password
        self.protocol = protocol

    def _jsonrpc(self, service: str, method: str, *args):
        payload = {
            "jsonrpc": "2.0",
            "method": "call",
            "params": {"service": service, "method": method, "args": list(args)},
            "id": 1,
        }
        with httpx.Client(timeout=30) as client:
            response = client.post(f"{self.base_url}/jsonrpc", json=payload)
        if response.status_code >= 400:
            raise AdapterError(f"odoo jsonrpc error status={response.status_code} body={response.text}")
        body = response.json()
        if body.get("error"):
            raise AdapterError(f"odoo jsonrpc returned error={body['error']}")
        return body.get("result")

    def _authenticate(self) -> int:
        if self.protocol == "jsonrpc":
            uid = self._jsonrpc("common", "login", self.database, self.username, self.password)
            if not uid:
                raise AdapterError("odoo authentication failed")
            return int(uid)

        common = xmlrpc.client.ServerProxy(f"{self.base_url}/xmlrpc/2/common")
        uid = common.authenticate(self.database, self.username, self.password, {})
        if not uid:
            raise AdapterError("odoo authentication failed")
        return int(uid)

    def _execute_kw(self, model: str, method: str, args: list | None = None, kwargs: dict | None = None):
        args = args or []
        kwargs = kwargs or {}
        uid = self._authenticate()

        if self.protocol == "jsonrpc":
            return self._jsonrpc(
                "object",
                "execute_kw",
                self.database,
                uid,
                self.password,
                model,
                method,
                args,
                kwargs,
            )

        models = xmlrpc.client.ServerProxy(f"{self.base_url}/xmlrpc/2/object")
        return models.execute_kw(self.database, uid, self.password, model, method, args, kwargs)

    def pull_products(self, since_cursor: str = "") -> dict:
        domain = []
        if since_cursor:
            domain.append(["write_date", ">=", since_cursor])
        fields = ["id", "name", "default_code", "barcode", "list_price", "write_date"]
        items = self._execute_kw(
            "product.template",
            "search_read",
            [domain],
            {"fields": fields, "limit": 500, "order": "write_date asc"},
        )
        return {"items": items, "next_cursor": items[-1]["write_date"] if items else ""}

    def push_product(self, payload: dict) -> dict:
        product = payload.get("product", payload)
        values = {
            "name": product.get("title", product.get("name", "Untitled")),
            "default_code": product.get("sku", ""),
            "barcode": product.get("barcode", ""),
            "list_price": product.get("price", 0),
        }
        product_id = product.get("odoo_id")
        if product_id:
            self._execute_kw("product.template", "write", [[int(product_id)], values])
            return {"status": "updated", "odoo_id": int(product_id)}
        created_id = self._execute_kw("product.template", "create", [values])
        return {"status": "created", "odoo_id": int(created_id)}

    def pull_orders(self, since_cursor: str = "") -> dict:
        domain = []
        if since_cursor:
            domain.append(["write_date", ">=", since_cursor])
        fields = ["id", "name", "state", "amount_total", "currency_id", "write_date"]
        items = self._execute_kw(
            "sale.order",
            "search_read",
            [domain],
            {"fields": fields, "limit": 500, "order": "write_date asc"},
        )
        return {"items": items, "next_cursor": items[-1]["write_date"] if items else ""}

    def ack_fulfillment(self, order_id: str, tracking: dict) -> dict:
        message = (
            f"Shipment confirmed: carrier={tracking.get('company', '')}, "
            f"number={tracking.get('number', '')}, url={tracking.get('url', '')}"
        )
        self._execute_kw("sale.order", "message_post", [[int(order_id)], {"body": message}])
        return {"status": "accepted", "order_id": order_id}

    def pull_refunds(self, since_cursor: str = "") -> dict:
        domain = [["move_type", "=", "out_refund"]]
        if since_cursor:
            domain.append(["write_date", ">=", since_cursor])
        fields = ["id", "name", "state", "amount_total", "write_date", "invoice_origin"]
        items = self._execute_kw(
            "account.move",
            "search_read",
            [domain],
            {"fields": fields, "limit": 500, "order": "write_date asc"},
        )
        return {"items": items, "next_cursor": items[-1]["write_date"] if items else ""}

    def rate_limit_strategy(self) -> dict:
        return {"mode": "fixed_window", "max_rps": 5}

    def pull_inbound_emails(
        self,
        *,
        since_cursor: str = "",
        target_address: str = "",
        source: str = "odoo_alias_fetchmail",
        limit: int = 200,
    ) -> dict:
        # mail.message is where Odoo stores inbound emails from aliases/fetchmail.
        domain: list = [["message_type", "=", "email"]]
        if since_cursor:
            domain.append(["date", ">=", since_cursor])

        if target_address:
            # Recipients are not consistently stored in one field across deployments.
            # We check common places where the target mailbox may appear.
            domain.extend(
                [
                    "|",
                    "|",
                    ["reply_to", "ilike", target_address],
                    ["body", "ilike", target_address],
                    ["subject", "ilike", target_address],
                ]
            )

        # Keep option for callers to request all email messages if needed.
        if source == "all_mail_messages":
            domain = [item for item in domain if item != ["message_type", "=", "email"]]

        fields = [
            "id",
            "message_id",
            "subject",
            "body",
            "email_from",
            "reply_to",
            "model",
            "res_id",
            "date",
            "create_date",
            "write_date",
        ]
        items = self._execute_kw(
            "mail.message",
            "search_read",
            [domain],
            {"fields": fields, "limit": int(limit), "order": "date asc, id asc"},
        )
        return {"items": items, "next_cursor": items[-1].get("date", "") if items else ""}


class AdapterFactory:
    @staticmethod
    def from_connection(connector: str, metadata: dict):
        if connector == "shopify":
            shop_domain = metadata.get("shop_domain", "")
            access_token = metadata.get("access_token", "")
            api_version = metadata.get("api_version", "2024-10")
            if not shop_domain or not access_token:
                raise AdapterError("missing Shopify credentials in credential vault")
            return ShopifyAdapter(
                shop_domain=shop_domain,
                access_token=access_token,
                api_version=api_version,
            )

        if connector == "odoo":
            base_url = metadata.get("base_url", "")
            database = metadata.get("database", "")
            username = metadata.get("username", "")
            password = metadata.get("password", "")
            protocol = metadata.get("protocol", "jsonrpc")
            if not base_url or not database or not username or not password:
                raise AdapterError("missing Odoo credentials in credential vault")
            return OdooAdapter(
                base_url=base_url,
                database=database,
                username=username,
                password=password,
                protocol=protocol,
            )

        raise AdapterError(f"unsupported connector={connector}")
