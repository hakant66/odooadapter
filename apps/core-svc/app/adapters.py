from __future__ import annotations

import base64
import re
from datetime import datetime, timezone
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

    @abstractmethod
    def create_vendor_bill_from_pdf(
        self,
        *,
        vendor_name: str = "PDF Import Vendor",
        pdf_base64: str,
        filename: str = "invoice.pdf",
    ) -> dict:
        raise NotImplementedError

    @abstractmethod
    def list_vendors(self, *, search: str = "", limit: int = 200) -> list[dict]:
        raise NotImplementedError

    @abstractmethod
    def create_vendor_bill_from_fields(
        self,
        *,
        vendor_name: str,
        bill_reference: str = "",
        bill_date: str = "",
        invoice_date: str = "",
        accounting_date: str = "",
        account_id: str = "",
        vat_percent: str = "",
        billing_id: str = "",
        currency: str = "",
        discount: str = "",
        payment_reference: str = "",
        recipient_bank: str = "",
        product: str = "",
        price: float | None = None,
        tax: str = "",
        amount: float | None = None,
        due_date: str = "",
        pdf_base64: str = "",
        pdf_filename: str = "invoice.pdf",
    ) -> dict:
        raise NotImplementedError

    @abstractmethod
    def find_vendor_bill_by_reference(self, *, bill_reference: str) -> int | None:
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

    def create_vendor_bill_from_pdf(
        self,
        *,
        vendor_name: str = "PDF Import Vendor",
        pdf_base64: str,
        filename: str = "invoice.pdf",
    ) -> dict:
        raise AdapterError("create_vendor_bill_from_pdf is not supported for shopify")

    def list_vendors(self, *, search: str = "", limit: int = 200) -> list[dict]:
        raise AdapterError("list_vendors is not supported for shopify")

    def create_vendor_bill_from_fields(
        self,
        *,
        vendor_name: str,
        bill_reference: str = "",
        bill_date: str = "",
        invoice_date: str = "",
        accounting_date: str = "",
        account_id: str = "",
        vat_percent: str = "",
        billing_id: str = "",
        currency: str = "",
        discount: str = "",
        payment_reference: str = "",
        recipient_bank: str = "",
        product: str = "",
        price: float | None = None,
        tax: str = "",
        amount: float | None = None,
        due_date: str = "",
        pdf_base64: str = "",
        pdf_filename: str = "invoice.pdf",
    ) -> dict:
        raise AdapterError("create_vendor_bill_from_fields is not supported for shopify")

    def find_vendor_bill_by_reference(self, *, bill_reference: str) -> int | None:
        raise AdapterError("find_vendor_bill_by_reference is not supported for shopify")


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

    @staticmethod
    def _normalize_odoo_datetime_cursor(raw_value: str) -> str:
        """
        Odoo domain datetime values must not include timezone suffixes.
        Returns `YYYY-MM-DD HH:MM:SS` in UTC when possible.
        """
        value = str(raw_value or "").strip()
        if not value:
            return ""
        if "T" not in value and len(value) >= 19:
            return value[:19]

        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            # Best effort normalization for unexpected strings.
            candidate = value.replace("T", " ")
            candidate = candidate.split("+", 1)[0]
            candidate = candidate.split("Z", 1)[0]
            return candidate[:19]

        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed.strftime("%Y-%m-%d %H:%M:%S")

    def pull_products(self, since_cursor: str = "") -> dict:
        domain = []
        if since_cursor:
            domain.append(["write_date", ">=", self._normalize_odoo_datetime_cursor(since_cursor)])
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
            domain.append(["write_date", ">=", self._normalize_odoo_datetime_cursor(since_cursor)])
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
            domain.append(["write_date", ">=", self._normalize_odoo_datetime_cursor(since_cursor)])
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
            domain.append(["date", ">=", self._normalize_odoo_datetime_cursor(since_cursor)])

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

    def _get_or_create_vendor(self, vendor_name: str) -> tuple[int, str]:
        existing = self._execute_kw(
            "res.partner",
            "search_read",
            [[["name", "ilike", vendor_name], ["supplier_rank", ">=", 0]]],
            {"fields": ["id", "name", "vat", "email", "ref"], "limit": 25},
        )
        if existing:
            normalized = vendor_name.strip().lower()
            exact = next((row for row in existing if str(row.get("name", "")).strip().lower() == normalized), None)
            if exact:
                return int(exact["id"]), "matched_exact_name"
            first = existing[0]
            return int(first["id"]), "matched_fuzzy_name"

        create_payloads = [
            {"name": vendor_name, "supplier_rank": 1},
            {"name": vendor_name},
            {"name": vendor_name, "is_company": True},
        ]
        last_error = None
        for payload in create_payloads:
            try:
                partner_id = self._execute_kw("res.partner", "create", [payload])
                return int(partner_id), "created_new_vendor"
            except AdapterError as exc:
                last_error = exc
                continue
        raise AdapterError(f"failed to create vendor partner: {last_error}")

    def create_vendor_bill_from_pdf(
        self,
        *,
        vendor_name: str = "PDF Import Vendor",
        pdf_base64: str,
        filename: str = "invoice.pdf",
    ) -> dict:
        normalized_pdf = str(pdf_base64 or "").strip()
        if "," in normalized_pdf and normalized_pdf.lower().startswith("data:"):
            normalized_pdf = normalized_pdf.split(",", 1)[1]
        if not normalized_pdf:
            raise AdapterError("pdf_base64 is required")
        try:
            base64.b64decode(normalized_pdf, validate=True)
        except Exception as exc:  # pragma: no cover - defensive for mixed b64 inputs
            raise AdapterError(f"invalid pdf_base64 payload: {exc}") from exc

        partner_id, vendor_strategy = self._get_or_create_vendor(vendor_name)
        values: dict = {
            "move_type": "in_invoice",
            "partner_id": partner_id,
        }

        try:
            bill_id = self._execute_kw("account.move", "create", [values])
        except AdapterError:
            # Fallback for Odoo setups that require explicit account mapping on invoice lines.
            fallback = {
                "move_type": "in_invoice",
                "partner_id": partner_id,
            }
            bill_id = self._execute_kw("account.move", "create", [fallback])

        attachment_id = self._execute_kw(
            "ir.attachment",
            "create",
            [
                {
                    "name": filename or "invoice.pdf",
                    "type": "binary",
                    "datas": normalized_pdf,
                    "res_model": "account.move",
                    "res_id": int(bill_id),
                    "mimetype": "application/pdf",
                }
            ],
        )
        return {
            "status": "created",
            "bill_id": int(bill_id),
            "attachment_id": int(attachment_id),
            "vendor_name": vendor_name,
            "debug": {
                "odoo_model": "account.move",
                "move_type": "in_invoice",
                "partner_id": partner_id,
                "vendor_strategy": vendor_strategy,
                "filename": filename or "invoice.pdf",
                "pdf_size_bytes_estimate": int(len(normalized_pdf) * 0.75),
            },
        }

    def list_vendors(self, *, search: str = "", limit: int = 200) -> list[dict]:
        domain: list = [["supplier_rank", ">=", 0]]
        if search:
            domain.extend(
                [
                    "|",
                    "|",
                    ["name", "ilike", search],
                    ["vat", "ilike", search],
                    ["email", "ilike", search],
                ]
            )
        rows = self._execute_kw(
            "res.partner",
            "search_read",
            [domain],
            {
                "fields": ["id", "name", "vat", "email", "ref", "supplier_rank"],
                "limit": int(limit),
                "order": "name asc",
            },
        )
        return [row for row in rows if isinstance(row, dict)]

    def _resolve_purchase_tax_ids(self, *, tax: str = "", vat_percent: str = "") -> list[int]:
        candidates: list[str] = []
        if tax and str(tax).strip():
            candidates.append(str(tax).strip())
        if vat_percent and str(vat_percent).strip():
            normalized = str(vat_percent).strip().replace("%", "")
            if normalized:
                candidates.extend([f"{normalized}%", f"{normalized} %", normalized])
        seen: set[str] = set()
        deduped = [item for item in candidates if not (item in seen or seen.add(item))]

        for candidate in deduped:
            rows = self._execute_kw(
                "account.tax",
                "search_read",
                [[["type_tax_use", "in", ["purchase", "none"]], ["name", "ilike", candidate]]],
                {"fields": ["id", "name"], "limit": 5, "order": "sequence asc, id asc"},
            )
            if isinstance(rows, list):
                ids = [int(row["id"]) for row in rows if isinstance(row, dict) and row.get("id")]
                if ids:
                    return [ids[0]]
        return []

    def _resolve_currency_id(self, currency: str = "") -> int | None:
        value = str(currency or "").strip()
        if not value:
            return None

        exact_code = value.upper()
        rows = self._execute_kw(
            "res.currency",
            "search_read",
            [[["name", "=", exact_code]]],
            {"fields": ["id", "name", "symbol"], "limit": 1},
        )
        if isinstance(rows, list) and rows:
            row = rows[0]
            if isinstance(row, dict) and row.get("id"):
                return int(row["id"])

        fuzzy = self._execute_kw(
            "res.currency",
            "search_read",
            [[["|", ["name", "ilike", value], ["symbol", "ilike", value]]]],
            {"fields": ["id", "name", "symbol"], "limit": 1},
        )
        if isinstance(fuzzy, list) and fuzzy:
            row = fuzzy[0]
            if isinstance(row, dict) and row.get("id"):
                return int(row["id"])
        return None

    def _find_existing_vendor_bill_by_ref(self, *, bill_reference: str, partner_id: int | None = None) -> int | None:
        ref = str(bill_reference or "").strip()
        if not ref:
            return None
        domain: list = [
            ["move_type", "=", "in_invoice"],
            ["ref", "=", ref],
        ]
        if partner_id:
            domain.append(["partner_id", "=", int(partner_id)])
        rows = self._execute_kw(
            "account.move",
            "search_read",
            [domain],
            {"fields": ["id", "ref", "partner_id"], "limit": 1, "order": "id desc"},
        )
        if isinstance(rows, list) and rows:
            row = rows[0]
            if isinstance(row, dict) and row.get("id"):
                return int(row["id"])
        return None

    @staticmethod
    def _normalize_odoo_date(value: str = "") -> str:
        raw = str(value or "").strip()
        if not raw:
            return ""

        if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
            return raw

        # Accept datetime-like values by taking the date portion.
        iso_like = re.match(r"^(\d{4}-\d{2}-\d{2})[T\s].*$", raw)
        if iso_like:
            return iso_like.group(1)

        cleaned = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", raw, flags=re.IGNORECASE)
        cleaned = cleaned.replace("Sept ", "Sep ").replace("sept ", "sep ")
        cleaned = re.sub(r"\s+", " ", cleaned).strip()

        # Named-month and explicit formats.
        for fmt in (
            "%b %d, %Y",
            "%B %d, %Y",
            "%b %d %Y",
            "%B %d %Y",
            "%d %b %Y",
            "%d %B %Y",
            "%b %d, %y",
            "%B %d, %y",
            "%d/%m/%Y",
            "%d/%m/%y",
            "%d-%m-%Y",
            "%d-%m-%y",
            "%Y/%m/%d",
            "%Y.%m.%d",
            "%d.%m.%Y",
            "%d.%m.%y",
        ):
            try:
                return datetime.strptime(cleaned, fmt).date().isoformat()
            except ValueError:
                continue

        # Numeric fallback for patterns like 03/07/26 or 3-7-2026.
        numeric = re.match(r"^(\d{1,2})[\/\.-](\d{1,2})[\/\.-](\d{2,4})$", cleaned)
        if numeric:
            first = int(numeric.group(1))
            second = int(numeric.group(2))
            year = int(numeric.group(3))
            if year < 100:
                year += 2000 if year <= 69 else 1900

            # Prefer day/month for ambiguous invoice formats; flip only when impossible.
            day, month = first, second
            if day > 31 or month > 12:
                day, month = second, first
            try:
                return datetime(year, month, day).date().isoformat()
            except ValueError:
                try:
                    return datetime(year, second, first).date().isoformat()
                except ValueError:
                    return ""

        return ""

    def create_vendor_bill_from_fields(
        self,
        *,
        vendor_name: str,
        bill_reference: str = "",
        bill_date: str = "",
        invoice_date: str = "",
        accounting_date: str = "",
        account_id: str = "",
        vat_percent: str = "",
        billing_id: str = "",
        currency: str = "",
        discount: str = "",
        payment_reference: str = "",
        recipient_bank: str = "",
        product: str = "",
        price: float | None = None,
        tax: str = "",
        amount: float | None = None,
        due_date: str = "",
        pdf_base64: str = "",
        pdf_filename: str = "invoice.pdf",
    ) -> dict:
        partner_id, vendor_strategy = self._get_or_create_vendor(vendor_name or "PDF Import Vendor")
        existing_bill_id = self._find_existing_vendor_bill_by_ref(
            bill_reference=bill_reference,
            partner_id=partner_id,
        )
        if existing_bill_id is not None:
            return {
                "status": "already_exists",
                "bill_id": int(existing_bill_id),
                "attachment_id": None,
                "vendor_name": vendor_name,
                "debug": {
                    "vendor_strategy": vendor_strategy,
                    "duplicate_ref": str(bill_reference or "").strip(),
                    "partner_id": partner_id,
                },
            }
        normalized_invoice_date = self._normalize_odoo_date(invoice_date)
        normalized_bill_date = self._normalize_odoo_date(bill_date)
        normalized_accounting_date = self._normalize_odoo_date(accounting_date)
        normalized_due_date = self._normalize_odoo_date(due_date)

        line_price = price if price is not None else amount
        line_values = {
            "name": product or "Imported from email PDF",
            "quantity": 1.0,
            "price_unit": float(line_price) if line_price is not None else 0.0,
        }
        discount_percent: float | None = None
        raw_discount = str(discount or "").strip()
        if raw_discount:
            cleaned_discount = raw_discount.replace("%", "").replace(",", "").strip()
            try:
                parsed_discount = float(cleaned_discount)
                if 0.0 <= parsed_discount <= 100.0:
                    discount_percent = parsed_discount
            except ValueError:
                discount_percent = None
        if discount_percent is not None:
            line_values["discount"] = discount_percent
        if str(account_id or "").strip().isdigit():
            line_values["account_id"] = int(str(account_id).strip())
        tax_ids = self._resolve_purchase_tax_ids(tax=tax, vat_percent=vat_percent)
        if tax_ids:
            line_values["tax_ids"] = [[6, 0, tax_ids]]

        values: dict = {
            "move_type": "in_invoice",
            "partner_id": partner_id,
            "invoice_line_ids": [[0, 0, line_values]],
        }
        currency_id = self._resolve_currency_id(currency)
        if currency_id is not None:
            values["currency_id"] = currency_id
        if bill_reference:
            values["ref"] = bill_reference
        if normalized_invoice_date:
            values["invoice_date"] = normalized_invoice_date
        if normalized_bill_date:
            values["invoice_date"] = values.get("invoice_date") or normalized_bill_date
        if normalized_accounting_date:
            values["date"] = normalized_accounting_date
        if payment_reference:
            values["invoice_payment_ref"] = payment_reference
        if normalized_due_date:
            values["invoice_date_due"] = normalized_due_date
        if billing_id:
            values["invoice_origin"] = billing_id
        narration_parts: list[str] = []
        if recipient_bank:
            narration_parts.append(f"Recipient bank: {recipient_bank}")
        if vat_percent and not tax_ids:
            narration_parts.append(f"VAT: {vat_percent}")
        if raw_discount and discount_percent is None:
            narration_parts.append(f"Discount: {raw_discount}")
        if narration_parts:
            values["narration"] = " | ".join(narration_parts)

        bill_id = self._execute_kw("account.move", "create", [values])
        attachment_id: int | None = None
        normalized_pdf = str(pdf_base64 or "").strip()
        if "," in normalized_pdf and normalized_pdf.lower().startswith("data:"):
            normalized_pdf = normalized_pdf.split(",", 1)[1]
        if normalized_pdf:
            try:
                base64.b64decode(normalized_pdf, validate=True)
                created_attachment_id = self._execute_kw(
                    "ir.attachment",
                    "create",
                    [
                        {
                            "name": pdf_filename or "invoice.pdf",
                            "type": "binary",
                            "datas": normalized_pdf,
                            "res_model": "account.move",
                            "res_id": int(bill_id),
                            "mimetype": "application/pdf",
                        }
                    ],
                )
                attachment_id = int(created_attachment_id)
            except Exception:
                attachment_id = None
        return {
            "status": "created",
            "bill_id": int(bill_id),
            "attachment_id": attachment_id,
            "vendor_name": vendor_name,
            "debug": {
                "vendor_strategy": vendor_strategy,
                "tax_raw": tax,
                "vat_percent": vat_percent,
                "tax_ids": tax_ids,
                "account_id": line_values.get("account_id"),
                "billing_id": billing_id,
                "currency": currency,
                "currency_id": currency_id,
                "discount": raw_discount,
                "discount_percent": discount_percent,
                "pdf_attached": bool(attachment_id),
                "pdf_filename": pdf_filename or "invoice.pdf",
                "line_price_used": line_values["price_unit"],
                "date_inputs": {
                    "bill_date_raw": bill_date,
                    "invoice_date_raw": invoice_date,
                    "accounting_date_raw": accounting_date,
                    "due_date_raw": due_date,
                    "bill_date": normalized_bill_date,
                    "invoice_date": normalized_invoice_date,
                    "accounting_date": normalized_accounting_date,
                    "due_date": normalized_due_date,
                },
            },
        }

    def find_vendor_bill_by_reference(self, *, bill_reference: str) -> int | None:
        return self._find_existing_vendor_bill_by_ref(bill_reference=bill_reference, partner_id=None)


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
