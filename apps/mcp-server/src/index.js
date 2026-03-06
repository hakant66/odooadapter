import crypto from "crypto";
import dotenv from "dotenv";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

dotenv.config({ path: "../../.env" });

const coreBase =
  process.env.CORE_API_INTERNAL_BASE ||
  process.env.NEXT_PUBLIC_CORE_API_BASE ||
  "http://localhost:8000";
const mcpWebhookBase = process.env.MCP_WEBHOOK_BASE || "http://localhost:3001";
const inboundWebhookSecret = process.env.INBOUND_EMAIL_WEBHOOK_SECRET || "replace-me";

async function jsonRequest(baseUrl, path, { method = "GET", body } = {}) {
  const response = await fetch(`${baseUrl}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store"
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = data?.detail || data?.error || `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

function asTextResult(data) {
  return {
    content: [{ type: "text", text: JSON.stringify(data, null, 2) }]
  };
}

const server = new McpServer({
  name: "odooadapter-control-plane",
  version: "0.1.0"
});

server.registerTool(
  "core_health",
  {
    title: "Core Health",
    description: "Check core service health status.",
    inputSchema: {}
  },
  async () => {
    const result = await jsonRequest(coreBase, "/health");
    return asTextResult(result);
  }
);

server.registerTool(
  "create_tenant",
  {
    title: "Create Tenant",
    description: "Create a tenant in the core service.",
    inputSchema: {
      name: z.string().min(2),
      slug: z.string().min(2)
    }
  },
  async ({ name, slug }) => {
    const result = await jsonRequest(coreBase, "/tenants", {
      method: "POST",
      body: { name, slug }
    });
    return asTextResult(result);
  }
);

server.registerTool(
  "create_odoo_connection",
  {
    title: "Create Odoo Connection",
    description: "Create or update an Odoo connector connection.",
    inputSchema: {
      tenant_id: z.string().min(1),
      external_account_id: z.string().min(1),
      base_url: z.string().url(),
      database: z.string().min(1),
      protocol: z.enum(["jsonrpc", "xmlrpc"]).default("jsonrpc"),
      username: z.string().min(1),
      password: z.string().min(1)
    }
  },
  async ({ tenant_id, external_account_id, base_url, database, protocol, username, password }) => {
    const result = await jsonRequest(coreBase, "/connections", {
      method: "POST",
      body: {
        tenant_id,
        connector: "odoo",
        external_account_id,
        credential_payload: { username, password },
        metadata: { base_url, database, protocol }
      }
    });
    return asTextResult(result);
  }
);

server.registerTool(
  "import_emails",
  {
    title: "Import Emails",
    description: "Queue Odoo inbound email pull job (IMPORT_EMAILS).",
    inputSchema: {
      tenant_id: z.string().min(1),
      connector: z.string().default("odoo"),
      since_cursor: z.string().default(""),
      target_address: z.string().default(""),
      source: z.string().default("odoo_alias_fetchmail"),
      limit: z.number().int().positive().max(500).default(200)
    }
  },
  async ({ tenant_id, connector, since_cursor, target_address, source, limit }) => {
    const result = await jsonRequest(coreBase, "/sync/emails/import", {
      method: "POST",
      body: {
        tenant_id,
        connector,
        since_cursor,
        target_address,
        source,
        limit
      }
    });
    return asTextResult(result);
  }
);

server.registerTool(
  "list_jobs",
  {
    title: "List Jobs",
    description: "List sync jobs, optionally scoped by tenant_id.",
    inputSchema: {
      tenant_id: z.string().default("")
    }
  },
  async ({ tenant_id }) => {
    const query = tenant_id ? `?tenant_id=${encodeURIComponent(tenant_id)}` : "";
    const result = await jsonRequest(coreBase, `/jobs${query}`);
    return asTextResult(result);
  }
);

server.registerTool(
  "list_emails",
  {
    title: "List Emails",
    description: "List synced canonical emails for a tenant.",
    inputSchema: {
      tenant_id: z.string().min(1),
      to_address: z.string().default(""),
      limit: z.number().int().positive().max(500).default(100)
    }
  },
  async ({ tenant_id, to_address, limit }) => {
    const query = new URLSearchParams({ tenant_id, limit: String(limit) });
    if (to_address) {
      query.set("to_address", to_address);
    }
    const result = await jsonRequest(coreBase, `/emails?${query.toString()}`);
    return asTextResult(result);
  }
);

server.registerTool(
  "send_inbound_email_webhook",
  {
    title: "Send Inbound Email Webhook",
    description: "Send a signed inbound email payload to MCP webhook endpoint.",
    inputSchema: {
      tenant_slug: z.string().min(1),
      connector: z.string().default("odoo"),
      target_address: z.string().default(""),
      email_payload: z.object({
        id: z.string().optional(),
        subject: z.string().default(""),
        from: z.string().default(""),
        to: z.string().default(""),
        body: z.string().default(""),
        received_at: z.string().optional()
      })
    }
  },
  async ({ tenant_slug, connector, target_address, email_payload }) => {
    const deliveryPayload = {
      ...email_payload,
      received_at: email_payload.received_at || new Date().toISOString()
    };

    const rawBody = Buffer.from(JSON.stringify(deliveryPayload));
    const signature = crypto
      .createHmac("sha256", inboundWebhookSecret)
      .update(rawBody)
      .digest("base64");

    const response = await fetch(`${mcpWebhookBase}/webhooks/email/inbound`, {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        "x-tenant-slug": tenant_slug,
        "x-connector": connector,
        "x-email-webhook-signature": signature,
        ...(target_address ? { "x-inbound-target-address": target_address } : {})
      },
      body: rawBody
    });

    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
      const detail = result?.detail || result?.error || `HTTP ${response.status}`;
      throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
    }

    return asTextResult(result);
  }
);

async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
}

main().catch((error) => {
  // eslint-disable-next-line no-console
  console.error("mcp-server fatal error:", error);
  process.exit(1);
});
