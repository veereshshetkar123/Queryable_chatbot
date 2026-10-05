import { requiredEnv } from "@/lib/env";
import librarySpec from "@/generated/spec.json";
import { resolveRequestedModel } from "@/lib/models";
import { runFunctionToolLoop } from "@/lib/tool-loop";
import { executeGetWeather, getWeatherTool } from "@/lib/tools/get-weather";
import { generateSystemPrompt } from "@openuidev/lang-core";
import { NextResponse } from "next/server";
import OpenAI from "openai";
import type {
  ResponseCreateParamsNonStreaming,
  ResponseInputItem,
  Tool,
} from "openai/resources/responses/responses";

const QUERYABLE_BACKEND_URL = "http://127.0.0.1:8000";

export async function POST(req: Request) {
  const {
    threadId,
    messages,
    model: requestedModel,
  } = (await req.json()) as {
    threadId?: string;
    messages?: ResponseInputItem[];
    model?: unknown;
  };

  if (!threadId) {
    return badRequest(
      "threadId is required — create the conversation first",
    );
  }

  if (!Array.isArray(messages) || messages.length === 0) {
    return badRequest(
      "messages must be a non-empty ResponseInputItem[]",
    );
  }

  const latestMessage = messages[messages.length - 1];

  /*
   * Send the user's question to the existing Queryable Agent.
   *
   * This keeps:
   *   Jev
   *   Gemini 2.5 Flash
   *   MongoDB
   *
   * as the actual database-answering system.
   */
  let queryableAnswer: string;

  try {
    const question =
      extractUserQuestion(latestMessage);

    if (!question) {
      return badRequest("Could not read the user's question.");
    }

    const backendResponse = await fetch(
      `${QUERYABLE_BACKEND_URL}/ask`,
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          question,
        }),
      },
    );

    if (!backendResponse.ok) {
      const errorText = await backendResponse.text();

      return NextResponse.json(
        {
          error: {
            message:
              "Queryable Agent backend returned an error.",
            details: errorText,
          },
        },
        { status: backendResponse.status },
      );
    }

    const backendData = await backendResponse.json();

    queryableAnswer =
      typeof backendData.answer === "string"
        ? backendData.answer
        : JSON.stringify(backendData.answer);
  } catch (error) {
    console.error(
      "QUERYABLE AGENT CONNECTION ERROR:",
      error,
    );

    return NextResponse.json(
      {
        error: {
          message:
            "Could not connect to the Queryable Agent backend. Make sure FastAPI is running.",
        },
      },
      { status: 500 },
    );
  }

  const model = resolveRequestedModel(requestedModel);

  if (!model) {
    return badRequest("model is not available in this agent");
  }

  /*
   * Send the real database answer to Thesys/OpenUI.
   *
   * Thesys is now responsible for presenting the result.
   * It should not invent or replace the database result.
   */
  const openuiInput: ResponseInputItem[] = [
    latestMessage,
    {
      type: "message",
      role: "user",
      content: [
        {
          type: "input_text",
          text: `
You are the presentation layer for a Queryable Database Agent.

The Queryable Agent has already processed the user's request
using Jev, Gemini, and MongoDB.

IMPORTANT:
- Treat the Queryable Agent result below as authoritative.
- Do not invent database values.
- Do not change numerical values.
- Do not claim database information that is not present in the result.
- Present the result clearly.
- When the data supports it, use an appropriate table, chart, KPI, or other OpenUI visualization.
- For a simple numerical answer, use a clean KPI/text presentation.
- For grouped or time-series data, choose an appropriate chart.
- Keep the response visually polished and concise.

USER QUESTION:
${extractUserQuestion(latestMessage)}

QUERYABLE AGENT RESULT:
${queryableAnswer}
`,
        },
      ],
    },
  ];

  const client = new OpenAI({
    baseURL: "https://api.thesys.dev/v1/embed",
    apiKey: requiredEnv("THESYS_API_KEY"),
  });

  const functionTools = {
    [getWeatherTool.name]: executeGetWeather,
  };

  const createParams: ResponseCreateParamsNonStreaming = {
    model,
    conversation: threadId,
    input: openuiInput,
    store: true,
    tools: [
      { type: "web_search" },
      { type: "image_search" } as unknown as Tool,
      getWeatherTool,
    ],
    instructions: generateSystemPrompt({
      cloud: true,
      library: librarySpec,
    }),
  };

  let stream: AsyncIterable<Record<string, unknown>>;

  try {
    stream = (await client.responses.create(
      {
        ...createParams,
        stream: true,
      },
      {
        signal: req.signal,
      },
    )) as unknown as AsyncIterable<Record<string, unknown>>;
  } catch (err) {
    const e = err as {
      status?: number;
      error?: unknown;
      message?: string;
    };

    return NextResponse.json(
      {
        error:
          e.error ?? {
            message: e.message ?? "upstream error",
          },
      },
      {
        status: e.status ?? 502,
      },
    );
  }

  const encoder = new TextEncoder();

  const body = new ReadableStream<Uint8Array>({
    async start(controller) {
      const enqueue = (
        event: Record<string, unknown>,
      ) => {
        controller.enqueue(
          encoder.encode(
            `data: ${JSON.stringify(event)}\n\n`,
          ),
        );
      };

      try {
        await runFunctionToolLoop({
          client,
          createParams,
          firstStream: stream,
          tools: functionTools,
          enqueue,
          signal: req.signal,
        });
      } catch (err) {
        enqueue({
          type: "error",
          message:
            err instanceof Error
              ? err.message
              : String(err),
        });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(body, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}

function extractUserQuestion(
  message: ResponseInputItem,
): string {
  const item = message as {
    role?: string;
    content?: unknown;
  };

  if (item.role !== "user") {
    return "";
  }

  if (typeof item.content === "string") {
    return item.content;
  }

  if (Array.isArray(item.content)) {
    return item.content
      .map((part) => {
        if (
          typeof part === "object" &&
          part !== null &&
          "text" in part &&
          typeof (part as { text?: unknown }).text ===
            "string"
        ) {
          return (part as { text: string }).text;
        }

        return "";
      })
      .filter(Boolean)
      .join("\n");
  }

  return "";
}

function badRequest(message: string): Response {
  return NextResponse.json(
    {
      error: {
        message,
      },
    },
    {
      status: 400,
    },
  );
}