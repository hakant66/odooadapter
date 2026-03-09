import { Buffer } from "buffer";
import dotenv from "dotenv";
import express from "express";
import morgan from "morgan";
import { google } from "googleapis";
import mammoth from "mammoth";
import pdfParse from "pdf-parse";
import { parse as parseCsvSync } from "csv-parse/sync";
import xlsx from "xlsx";
import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";

dotenv.config({ path: "../../.env" });

const DEFAULT_MAILBOX = "INBOX";
const MAX_EXTRACTED_TEXT_CHARS = Number(process.env.EMAIL_MCP_MAX_EXTRACTED_TEXT_CHARS || 12000);
const HTTP_PORT = Number(process.env.EMAIL_MCP_HTTP_PORT || 3010);
const TRANSPORT_MODE = String(process.env.EMAIL_MCP_TRANSPORT || "http").toLowerCase();

function loadAccountConfig(accountId) {
  const raw = process.env.GMAIL_ACCOUNTS_JSON || "{}";
  let parsed = {};
  try {
    parsed = JSON.parse(raw);
  } catch {
    parsed = {};
  }

  const account = parsed[accountId] || parsed.default || null;
  if (!account) {
    throw new Error(`account_id not found in GMAIL_ACCOUNTS_JSON: ${accountId}`);
  }

  for (const key of ["client_id", "client_secret", "refresh_token"]) {
    if (!account[key]) {
      throw new Error(`missing ${key} for account_id=${accountId}`);
    }
  }

  return {
    clientId: account.client_id,
    clientSecret: account.client_secret,
    refreshToken: account.refresh_token,
    accessToken: account.access_token || undefined,
    redirectUri: account.redirect_uri || "urn:ietf:wg:oauth:2.0:oob"
  };
}

function getGmailClient(accountId, oauthConfig = null) {
  const account = oauthConfig
    ? {
        clientId: oauthConfig.client_id,
        clientSecret: oauthConfig.client_secret,
        refreshToken: oauthConfig.refresh_token,
        accessToken: oauthConfig.access_token || undefined,
        redirectUri: oauthConfig.redirect_uri || "urn:ietf:wg:oauth:2.0:oob"
      }
    : loadAccountConfig(accountId);
  const auth = new google.auth.OAuth2(account.clientId, account.clientSecret, account.redirectUri);
  auth.setCredentials({
    refresh_token: account.refreshToken,
    access_token: account.accessToken
  });

  const gmail = google.gmail({ version: "v1", auth });
  return { gmail, account };
}

function headerValue(headers, name) {
  const found = (headers || []).find((h) => h?.name?.toLowerCase() === name.toLowerCase());
  return found?.value || "";
}

function toAddressList(value) {
  if (!value) {
    return [];
  }
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function decodeBase64Url(input) {
  if (!input) {
    return Buffer.from("");
  }
  const normalized = input.replace(/-/g, "+").replace(/_/g, "/");
  const padded = normalized + "=".repeat((4 - (normalized.length % 4)) % 4);
  return Buffer.from(padded, "base64");
}

function bodyTextFromPayload(payload) {
  if (!payload) {
    return "";
  }

  const parts = [];

  function walk(part) {
    if (!part) {
      return;
    }

    if (part?.mimeType === "text/plain" && part.body?.data) {
      parts.push(decodeBase64Url(part.body.data).toString("utf8"));
    }

    if (Array.isArray(part.parts)) {
      for (const child of part.parts) {
        walk(child);
      }
    }
  }

  walk(payload);

  if (parts.length > 0) {
    return parts.join("\n\n").trim();
  }

  if (payload.body?.data) {
    return decodeBase64Url(payload.body.data).toString("utf8").trim();
  }

  return "";
}

function attachmentCandidates(payload) {
  const out = [];

  function walk(part) {
    if (!part) {
      return;
    }

    const filename = part.filename || "";
    const body = part.body || {};
    const hasAttachmentId = Boolean(body.attachmentId);
    const hasInlineData = Boolean(body.data && filename);
    const isAttachment = filename && (hasAttachmentId || hasInlineData);

    if (isAttachment) {
      out.push({
        filename,
        mimeType: part.mimeType || "application/octet-stream",
        size: Number(body.size || 0),
        attachmentId: body.attachmentId || "",
        inlineData: body.data || "",
        inline: String(part.contentDisposition || "").toLowerCase() === "inline"
      });
    }

    if (Array.isArray(part.parts)) {
      for (const child of part.parts) {
        walk(child);
      }
    }
  }

  if (payload) {
    walk(payload);
  }
  return out;
}

async function resolveAttachmentBytes(gmail, messageId, candidate) {
  if (candidate.inlineData) {
    return decodeBase64Url(candidate.inlineData);
  }

  if (!candidate.attachmentId) {
    return Buffer.from("");
  }

  const response = await gmail.users.messages.attachments.get({
    userId: "me",
    messageId,
    id: candidate.attachmentId
  });

  return decodeBase64Url(response.data?.data || "");
}

function trimText(text) {
  if (!text) {
    return "";
  }
  if (text.length <= MAX_EXTRACTED_TEXT_CHARS) {
    return text;
  }
  return `${text.slice(0, MAX_EXTRACTED_TEXT_CHARS)}\n...[truncated]`;
}

async function extractAttachmentText(buffer, mimeType, filename) {
  const lowerName = String(filename || "").toLowerCase();
  const lowerMime = String(mimeType || "").toLowerCase();

  if (lowerMime === "application/pdf" || lowerName.endsWith(".pdf")) {
    const parsed = await pdfParse(buffer);
    return { text: trimText(parsed.text || ""), kind: "pdf" };
  }

  if (
    lowerMime === "application/vnd.openxmlformats-officedocument.wordprocessingml.document" ||
    lowerName.endsWith(".docx")
  ) {
    const parsed = await mammoth.extractRawText({ buffer });
    return { text: trimText(parsed.value || ""), kind: "docx" };
  }

  if (lowerMime === "text/csv" || lowerName.endsWith(".csv")) {
    const raw = buffer.toString("utf8");
    const rows = parseCsvSync(raw, { relax_quotes: true, skip_empty_lines: true });
    const preview = rows.slice(0, 30).map((row) => row.join(",")).join("\n");
    return { text: trimText(preview), kind: "csv" };
  }

  if (
    lowerMime === "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" ||
    lowerName.endsWith(".xlsx")
  ) {
    const workbook = xlsx.read(buffer, { type: "buffer" });
    const lines = [];
    for (const sheetName of workbook.SheetNames.slice(0, 3)) {
      lines.push(`Sheet: ${sheetName}`);
      const csv = xlsx.utils.sheet_to_csv(workbook.Sheets[sheetName]);
      lines.push(csv.split("\n").slice(0, 30).join("\n"));
      lines.push("");
    }
    return { text: trimText(lines.join("\n")), kind: "xlsx" };
  }

  return { text: "", kind: "unsupported" };
}

function normalizeMessage(message, mailbox, includeHeaders) {
  const payload = message.payload || {};
  const headers = payload.headers || [];
  const from = headerValue(headers, "From");
  const to = headerValue(headers, "To");
  const cc = headerValue(headers, "Cc");
  const subject = headerValue(headers, "Subject");
  const date = headerValue(headers, "Date") || message.internalDate || "";

  const normalized = {
    message_id: message.id || "",
    thread_id: message.threadId || "",
    date,
    from,
    to: toAddressList(to),
    cc: toAddressList(cc),
    subject,
    snippet: message.snippet || "",
    mailbox,
    provider: "gmail"
  };

  if (includeHeaders) {
    normalized.headers = Object.fromEntries(headers.map((h) => [h.name || "", h.value || ""]));
  }

  return normalized;
}

function normalizeSubjectToQuery(subject) {
  const removedTokens = [];
  let working = String(subject || "").trim();

  const prefixRegex = /^(re|fw|fwd)\s*:\s*/i;
  while (prefixRegex.test(working)) {
    const match = working.match(prefixRegex);
    if (match) {
      removedTokens.push(match[0].trim());
      working = working.replace(prefixRegex, "").trim();
    }
  }

  const bracketed = working.match(/\[[^\]]+\]/g) || [];
  if (bracketed.length) {
    removedTokens.push(...bracketed);
    working = working.replace(/\[[^\]]+\]/g, " ").trim();
  }

  working = working
    .replace(/[|_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();

  return {
    query: working,
    normalization_applied: working !== subject,
    tokens_removed: removedTokens
  };
}

const toolSchemas = {
  "email.test_connection": {
    account_id: z.string().min(1),
    oauth: z
      .object({
        client_id: z.string(),
        client_secret: z.string(),
        refresh_token: z.string(),
        access_token: z.string().optional(),
        redirect_uri: z.string().optional()
      })
      .optional(),
    mailbox: z.string().default(DEFAULT_MAILBOX)
  },
  "email.fetch_messages": {
    account_id: z.string().min(1),
    oauth: z
      .object({
        client_id: z.string(),
        client_secret: z.string(),
        refresh_token: z.string(),
        access_token: z.string().optional(),
        redirect_uri: z.string().optional()
      })
      .optional(),
    mailbox: z.string().default(DEFAULT_MAILBOX),
    window_days: z.number().int().positive().max(90).default(7),
    max_messages: z.number().int().positive().max(200).default(20),
    target_to_address: z.string().default(""),
    include_headers: z.boolean().default(false),
    include_snippet: z.boolean().default(true)
  },
  "email.get_message": {
    account_id: z.string().min(1),
    oauth: z
      .object({
        client_id: z.string(),
        client_secret: z.string(),
        refresh_token: z.string(),
        access_token: z.string().optional(),
        redirect_uri: z.string().optional()
      })
      .optional(),
    message_id: z.string().min(1),
    mailbox: z.string().default(DEFAULT_MAILBOX),
    include_headers: z.boolean().default(true)
  },
  "email.get_attachments": {
    account_id: z.string().min(1),
    oauth: z
      .object({
        client_id: z.string(),
        client_secret: z.string(),
        refresh_token: z.string(),
        access_token: z.string().optional(),
        redirect_uri: z.string().optional()
      })
      .optional(),
    message_id: z.string().min(1),
    extract_text: z.boolean().default(true),
    include_content_base64: z.boolean().default(false)
  },
  "email.process_subject_query": {
    subject: z.string().default(""),
    use_raw_subject: z.boolean().default(false)
  }
};

const toolHandlers = {
  "email.test_connection": async ({ account_id, oauth }) => {
    const { gmail } = getGmailClient(account_id, oauth || null);
    const profile = await gmail.users.getProfile({ userId: "me" });
    return {
      ok: true,
      provider: "gmail",
      message: "Connection successful",
      email_address: profile.data?.emailAddress || ""
    };
  },

  "email.fetch_messages": async ({ account_id, oauth, mailbox, window_days, max_messages, target_to_address, include_headers, include_snippet }) => {
    const { gmail } = getGmailClient(account_id, oauth || null);

    const queryTerms = [`newer_than:${window_days}d`];
    const filterApplied = Boolean(target_to_address);
    if (filterApplied) {
      queryTerms.push(`to:${target_to_address}`);
    }

    const listResponse = await gmail.users.messages.list({
      userId: "me",
      labelIds: mailbox ? [mailbox] : undefined,
      maxResults: max_messages,
      q: queryTerms.join(" ")
    });

    const candidate = listResponse.data.messages || [];
    const messages = [];

    for (const item of candidate) {
      if (!item.id) {
        continue;
      }
      const full = await gmail.users.messages.get({
        userId: "me",
        id: item.id,
        format: "full"
      });

      const normalized = normalizeMessage(full.data || {}, mailbox, include_headers);
      if (!include_snippet) {
        delete normalized.snippet;
      }

      if (
        target_to_address &&
        normalized.to.every((addr) => !addr.toLowerCase().includes(target_to_address.toLowerCase()))
      ) {
        continue;
      }

      messages.push(normalized);
    }

    return {
      messages,
      count: messages.length,
      filter_applied: filterApplied,
      debug: {
        candidate_count: candidate.length,
        post_filter_count: messages.length
      }
    };
  },

  "email.get_message": async ({ account_id, oauth, message_id, mailbox, include_headers }) => {
    const { gmail } = getGmailClient(account_id, oauth || null);
    const response = await gmail.users.messages.get({
      userId: "me",
      id: message_id,
      format: "full"
    });

    const message = response.data || {};
    const normalized = normalizeMessage(message, mailbox, include_headers);
    normalized.body = bodyTextFromPayload(message.payload || {});

    const attachments = attachmentCandidates(message.payload || {}).map((a) => ({
      filename: a.filename,
      mime_type: a.mimeType,
      size: a.size,
      inline: a.inline,
      has_attachment_id: Boolean(a.attachmentId)
    }));

    return {
      ...normalized,
      mime_parts: {
        attachments
      }
    };
  },

  "email.get_attachments": async ({ account_id, oauth, message_id, extract_text, include_content_base64 }) => {
    const { gmail } = getGmailClient(account_id, oauth || null);
    const response = await gmail.users.messages.get({
      userId: "me",
      id: message_id,
      format: "full"
    });

    const payload = response.data?.payload || {};
    const candidates = attachmentCandidates(payload);
    const attachments = [];

    for (const candidate of candidates) {
      const bytes = await resolveAttachmentBytes(gmail, message_id, candidate);
      const base = {
        id: candidate.attachmentId || `${message_id}:${candidate.filename}:${candidate.size}`,
        filename: candidate.filename || "(unnamed)",
        mime_type: candidate.mimeType,
        size: bytes.length || candidate.size || 0,
        inline: candidate.inline,
        content_base64: include_content_base64 ? bytes.toString("base64") : "",
        extracted_text: "",
        extraction_status: "skipped"
      };

      if (!extract_text) {
        attachments.push(base);
        continue;
      }

      try {
        const extracted = await extractAttachmentText(bytes, candidate.mimeType, candidate.filename);
        attachments.push({
          ...base,
          extracted_text: extracted.text,
          extraction_status: extracted.kind === "unsupported" ? "unsupported" : "ok",
          extraction_type: extracted.kind
        });
      } catch (error) {
        attachments.push({
          ...base,
          extraction_status: "error",
          extraction_error: String(error)
        });
      }
    }

    return {
      message_id,
      attachments,
      count: attachments.length
    };
  },

  "email.process_subject_query": async ({ subject, use_raw_subject }) => {
    if (use_raw_subject) {
      return {
        query: subject,
        normalization_applied: false,
        tokens_removed: []
      };
    }
    return normalizeSubjectToQuery(subject);
  }
};

async function invokeTool(toolName, input) {
  const schemaShape = toolSchemas[toolName];
  const handler = toolHandlers[toolName];

  if (!schemaShape || !handler) {
    throw new Error(`unknown tool: ${toolName}`);
  }

  const parsed = z.object(schemaShape).parse(input || {});
  return handler(parsed);
}

function toMcpText(result) {
  return {
    content: [{ type: "text", text: JSON.stringify(result, null, 2) }]
  };
}

async function startStdioServer() {
  const server = new McpServer({ name: "sold-item-email-mcp", version: "0.2.0" });

  for (const [toolName, schemaShape] of Object.entries(toolSchemas)) {
    server.registerTool(
      toolName,
      {
        title: toolName,
        description: `Execute ${toolName}`,
        inputSchema: schemaShape
      },
      async (input) => {
        const result = await invokeTool(toolName, input);
        return toMcpText(result);
      }
    );
  }

  const transport = new StdioServerTransport();
  await server.connect(transport);
}

function startHttpServer() {
  const app = express();
  app.use(morgan("tiny"));
  app.use(express.json({ limit: "10mb" }));

  app.get("/health", (_req, res) => {
    res.json({ service: "sold-item-email-mcp", ok: true, transport: "http" });
  });

  app.get("/tools", (_req, res) => {
    res.json({ tools: Object.keys(toolHandlers) });
  });

  app.post("/tools/:toolName", async (req, res) => {
    const { toolName } = req.params;
    const input = req.body?.input || req.body || {};
    try {
      const result = await invokeTool(toolName, input);
      res.json({ ok: true, result });
    } catch (error) {
      res.status(400).json({ ok: false, error: String(error) });
    }
  });

  app.listen(HTTP_PORT, () => {
    // eslint-disable-next-line no-console
    console.log(`sold-item-email-mcp http listening on :${HTTP_PORT}`);
  });
}

async function main() {
  if (TRANSPORT_MODE === "stdio") {
    await startStdioServer();
    return;
  }

  if (TRANSPORT_MODE === "both") {
    startHttpServer();
    await startStdioServer();
    return;
  }

  startHttpServer();
}

main().catch((error) => {
  // eslint-disable-next-line no-console
  console.error("sold-item-email-mcp fatal error:", error);
  process.exit(1);
});
