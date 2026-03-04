import crypto from "crypto";
import dotenv from "dotenv";
import express from "express";
import Redis from "ioredis";
import morgan from "morgan";

dotenv.config({ path: "../../.env" });

const app = express();
const port = Number(process.env.MCP_PORT || 3001);
const redisUrl = process.env.REDIS_URL || "redis://localhost:6379/0";
const shopifyWebhookSecret = process.env.SHOPIFY_WEBHOOK_SECRET || "replace-me";
const inboundEmailWebhookSecret = process.env.INBOUND_EMAIL_WEBHOOK_SECRET || "replace-me";

const redis = new Redis(redisUrl, { lazyConnect: false });

app.use(morgan("tiny"));
app.use(express.json({ limit: "2mb", verify: rawBodySaver }));

function rawBodySaver(req, _res, buf) {
  req.rawBody = buf;
}

function verifyShopifyWebhook(req) {
  return verifyHmacBase64(req.header("x-shopify-hmac-sha256"), shopifyWebhookSecret, req.rawBody);
}

function verifyInboundEmailWebhook(req) {
  return verifyHmacBase64(req.header("x-email-webhook-signature"), inboundEmailWebhookSecret, req.rawBody);
}

function verifyHmacBase64(signature, secret, rawBody) {
  const computed = crypto
    .createHmac("sha256", secret)
    .update(rawBody || Buffer.from(""))
    .digest("base64");

  if (!signature) {
    return false;
  }

  try {
    return crypto.timingSafeEqual(Buffer.from(signature), Buffer.from(computed));
  } catch {
    return false;
  }
}

function normalizeShopifyEvent(req) {
  const topic = req.header("x-shopify-topic") || "unknown";
  const deliveryId = req.header("x-shopify-webhook-id") || crypto.randomUUID();
  const tenantSlug = req.header("x-tenant-slug") || req.query.tenant_slug || "";

  return {
    tenant_slug: tenantSlug,
    connector: "shopify",
    event_type: topic,
    delivery_id: deliveryId,
    payload: req.body,
    received_at: new Date().toISOString()
  };
}

function normalizeInboundEmailEvent(req) {
  const deliveryId = req.header("x-email-delivery-id") || req.body?.id || crypto.randomUUID();
  const tenantSlug = req.header("x-tenant-slug") || req.query.tenant_slug || "";
  const connector = req.header("x-connector") || "odoo";
  const payload = {
    ...req.body,
    delivery_id: deliveryId,
    target_address: req.header("x-inbound-target-address") || req.body?.target_address || req.body?.to || "",
    received_at: req.body?.received_at || new Date().toISOString()
  };

  return {
    tenant_slug: tenantSlug,
    connector,
    event_type: "emails/inbound",
    delivery_id: deliveryId,
    payload,
    received_at: new Date().toISOString()
  };
}

app.get("/health", (_req, res) => {
  res.json({ service: "mcp", ok: true });
});

app.post("/webhooks/shopify", async (req, res) => {
  if (!verifyShopifyWebhook(req)) {
    return res.status(401).json({ error: "invalid webhook signature" });
  }

  const envelope = normalizeShopifyEvent(req);
  if (!envelope.tenant_slug) {
    return res.status(400).json({ error: "missing tenant slug in x-tenant-slug header or tenant_slug query" });
  }

  try {
    await redis.rpush("sync:events", JSON.stringify(envelope));
    return res.status(200).json({ accepted: true });
  } catch (error) {
    return res.status(503).json({ error: "queue unavailable", details: String(error) });
  }
});

app.post("/webhooks/email/inbound", async (req, res) => {
  if (!verifyInboundEmailWebhook(req)) {
    return res.status(401).json({ error: "invalid inbound email webhook signature" });
  }

  const envelope = normalizeInboundEmailEvent(req);
  if (!envelope.tenant_slug) {
    return res.status(400).json({ error: "missing tenant slug in x-tenant-slug header or tenant_slug query" });
  }

  try {
    await redis.rpush("sync:events", JSON.stringify(envelope));
    return res.status(200).json({ accepted: true });
  } catch (error) {
    return res.status(503).json({ error: "queue unavailable", details: String(error) });
  }
});

app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`mcp listening on :${port}`);
});
