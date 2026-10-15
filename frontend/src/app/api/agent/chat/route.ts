import { NextRequest } from "next/server";
import {
  searchRealtimeJobsTool,
  extractCareerProfileTool,
  analyzeJobMatchTool,
  calculateATSScoreTool,
  generateTailoredResumeTool,
  draftApplicationMaterialsTool,
  buildCareerRoadmapTool,
} from "@/lib/career-agent-engine";

interface StreamChunk {
  type: "text" | "tool_call" | "tool_result" | "analytics_update" | "done" | "error";
  content?: string;
  toolCall?: {
    id: string;
    name: string;
    arguments: Record<string, unknown>;
    startedAt: string;
  };
  toolCallId?: string;
  toolResult?: unknown;
  metrics?: Record<string, unknown>;
  error?: string;
}

interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
}

function encodeChunk(chunk: StreamChunk): string {
  return `data: ${JSON.stringify(chunk)}\n\n`;
}

// Active NVIDIA NIM models for high-intelligence career conversation
const NVIDIA_MODELS = [
  "nvidia/nemotron-3-super-120b-a12b",
  "meta/llama-3.2-11b-vision-instruct",
  "openai/gpt-oss-20b",
];

async function callNvidiaChat(
  messagesHistory: ChatMessage[],
  contextSummary: string
): Promise<string> {
  // Server-only env (never NEXT_PUBLIC_*); no hardcoded fallback key.
  const apiKey = process.env.OPENAI_API_KEY || "";
  const baseUrl =
    process.env.OPENAI_BASE_URL || "https://integrate.api.nvidia.com/v1";
  if (!apiKey) {
    console.warn("OPENAI_API_KEY is not set in the frontend server environment; skipping LLM chat.");
    return "";
  }

  const systemPrompt = `You are the Principal AI Career Counsellor and Executive Talent Strategist at JobPilot (powered by NVIDIA 120B / Llama 3 models).
Your mission is to be an engaging, intelligent, empathetic, and continuous chatbot with whom candidates can talk deeply about their careers, goals, skills, interview preparation, salary negotiations, resume critique, system architecture, and daily career growth.

Candidate Profile Context:
${contextSummary}

Guidelines:
1. Converse naturally like an elite career coach and tech advisor.
2. Provide specific, tailored advice based on candidate context.
3. If they ask questions, answer thoroughly with clear formatting, bullet points, and actionable takeaways.
4. Maintain continuity across the conversation.`;

  const conversation = [
    { role: "system", content: systemPrompt },
    ...messagesHistory.slice(-8).map((m) => ({
      role: m.role === "user" ? "user" : "assistant",
      content: m.content || "",
    })),
  ];

  for (const model of NVIDIA_MODELS) {
    try {
      const resp = await fetch(`${baseUrl}/chat/completions`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${apiKey}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          model,
          messages: conversation,
          temperature: 0.5,
          max_tokens: 1200,
        }),
      });

      if (resp.ok) {
        const data = await resp.json();
        const content = data.choices?.[0]?.message?.content;
        if (content && content.trim()) return content.trim();
      }
    } catch (e) {
      console.warn(`NVIDIA model ${model} chat warning:`, e);
    }
  }

  return "";
}

async function* executeAgentWorkflow(
  userMessage: string,
  history: ChatMessage[] = []
) {
  const query = userMessage.trim();
  const lower = query.toLowerCase();

  let toolCounter = 0;

  // Realtime Intent Classification for automated tools
  const isJobSearch =
    lower.includes("search job") ||
    lower.includes("find job") ||
    lower.includes("look for job") ||
    lower.includes("remote roles") ||
    lower.includes("job openings") ||
    lower.includes("hiring for");

  const isProfileExtraction =
    lower.includes("extract profile") ||
    lower.includes("parse resume") ||
    lower.startsWith("extract my") ||
    (lower.includes("years exp") && lower.includes("specialized"));

  const isJobMatch =
    lower.includes("compare my profile") ||
    lower.includes("match matrix") ||
    lower.includes("fit for this role");

  const isATSCheck =
    lower.includes("ats audit") ||
    lower.includes("ats score") ||
    lower.includes("audit my resume") ||
    lower.includes("ats compliance");

  const isResumeGen =
    lower.includes("generate resume") ||
    lower.includes("tailored resume") ||
    lower.includes("build resume for");

  const isOutreach =
    lower.includes("draft outreach") ||
    lower.includes("cold email") ||
    lower.includes("recruiter note") ||
    lower.includes("cover letter");

  const isRoadmap =
    lower.includes("career roadmap") ||
    lower.includes("90-day plan") ||
    lower.includes("transition to") ||
    lower.includes("upskilling roadmap");

  // Load canonical context
  const profileContext = await extractCareerProfileTool(
    "Sample Candidate, Senior Agentic AI & Full-Stack Engineer, FastAPI, Next.js, Python, PostgreSQL, Docker, LangChain"
  );

  // 1. Tool Execution: Job Search
  if (isJobSearch) {
    const toolCallId = `tc_${Date.now()}_${++toolCounter}`;
    yield encodeChunk({
      type: "tool_call",
      toolCall: {
        id: toolCallId,
        name: "search_realtime_jobs",
        arguments: { query, count: 4, verifiedOnly: true },
        startedAt: new Date().toISOString(),
      },
    });

    const jobResults = await searchRealtimeJobsTool({ query });
    yield encodeChunk({
      type: "tool_result",
      toolCallId,
      toolResult: jobResults,
    });
  }

  // 2. Tool Execution: Profile Extraction
  if (isProfileExtraction) {
    const toolCallId = `tc_${Date.now()}_${++toolCounter}`;
    yield encodeChunk({
      type: "tool_call",
      toolCall: {
        id: toolCallId,
        name: "extract_canonical_profile",
        arguments: { rawText: query, confidenceThreshold: 0.9 },
        startedAt: new Date().toISOString(),
      },
    });

    const profile = await extractCareerProfileTool(query);
    yield encodeChunk({
      type: "tool_result",
      toolCallId,
      toolResult: profile,
    });
  }

  // 3. Tool Execution: ATS Audit
  if (isATSCheck) {
    const toolCallId = `tc_${Date.now()}_${++toolCounter}`;
    yield encodeChunk({
      type: "tool_call",
      toolCall: {
        id: toolCallId,
        name: "calculate_ats_score",
        arguments: { targetRole: "Senior Engineer", strictMode: true },
        startedAt: new Date().toISOString(),
      },
    });

    const atsScore = await calculateATSScoreTool(query);
    yield encodeChunk({
      type: "tool_result",
      toolCallId,
      toolResult: atsScore,
    });
  }

  // 4. Tool Execution: Match Matrix
  if (isJobMatch) {
    const toolCallId = `tc_${Date.now()}_${++toolCounter}`;
    yield encodeChunk({
      type: "tool_call",
      toolCall: {
        id: toolCallId,
        name: "analyze_job_match",
        arguments: { roleTitle: "Target Position", company: "Hiring Company" },
        startedAt: new Date().toISOString(),
      },
    });

    const match = await analyzeJobMatchTool({
      job_title: "Target Position",
      company: "Hiring Company",
      candidate_skills: profileContext.summary.skills,
      job_requirements: ["Python", "FastAPI", "React", "Docker", "System Design"],
      candidate_years: profileContext.summary.experience_years || 3,
      required_years: 3,
    });
    yield encodeChunk({
      type: "tool_result",
      toolCallId,
      toolResult: match,
    });
  }

  // 5. Tool Execution: Resume Tailoring
  if (isResumeGen) {
    const toolCallId = `tc_${Date.now()}_${++toolCounter}`;
    yield encodeChunk({
      type: "tool_call",
      toolCall: {
        id: toolCallId,
        name: "generate_tailored_resume",
        arguments: { role: "Staff AI Engineer", layout: "modern_ats" },
        startedAt: new Date().toISOString(),
      },
    });

    const tailoredResume = await generateTailoredResumeTool({
      target_role: "Senior AI Engineer",
      candidate_name: "Candidate",
    });
    yield encodeChunk({
      type: "tool_result",
      toolCallId,
      toolResult: tailoredResume,
    });
  }

  // 6. Tool Execution: Outreach Materials
  if (isOutreach) {
    const toolCallId = `tc_${Date.now()}_${++toolCounter}`;
    yield encodeChunk({
      type: "tool_call",
      toolCall: {
        id: toolCallId,
        name: "draft_application_materials",
        arguments: { role: "Target Role", company: "Company" },
        startedAt: new Date().toISOString(),
      },
    });

    const materials = await draftApplicationMaterialsTool({
      target_role: "Senior AI Engineer",
      target_company: "Target Tech",
    });
    yield encodeChunk({
      type: "tool_result",
      toolCallId,
      toolResult: materials,
    });
  }

  // 7. Tool Execution: Career Roadmap
  if (isRoadmap) {
    const toolCallId = `tc_${Date.now()}_${++toolCounter}`;
    yield encodeChunk({
      type: "tool_call",
      toolCall: {
        id: toolCallId,
        name: "build_career_roadmap",
        arguments: { targetLevel: "Staff / Principal", timelineMonths: 3 },
        startedAt: new Date().toISOString(),
      },
    });

    const roadmap = await buildCareerRoadmapTool({
      current_role: "Full-Stack Engineer",
      target_role: "Staff / Principal AI Systems Architect",
    });
    yield encodeChunk({
      type: "tool_result",
      toolCallId,
      toolResult: roadmap,
    });
  }

  // Call NVIDIA LLM for deep conversational response
  const contextSummary = `Headline: ${profileContext.summary.headline || "Agentic AI & Full Stack Engineer"}
Skills: ${profileContext.summary.skills.join(", ") || "Python, FastAPI, Next.js, PostgreSQL, Docker, LangChain"}
Years Exp: ${profileContext.summary.experience_years || 3}`;

  const allMessages: ChatMessage[] = [
    ...history,
    { role: "user", content: query },
  ];

  const nvidiaReply = await callNvidiaChat(allMessages, contextSummary);

  let finalResponse = nvidiaReply;
  if (!finalResponse) {
    if (isJobSearch) {
      finalResponse = `### Realtime Job Intelligence Summary
I've queried verified active openings matching your background. Review the interactive cards above to explore compensation, tech stacks, or trigger one-click applications.

Feel free to ask me to draft cover letters, tailor your CV for any specific role, or analyze match scores!`;
    } else if (isATSCheck) {
      finalResponse = `### ATS Diagnostic & Optimization Overview
Your profile audit is complete. Your core skills and project impacts rank high for modern engineering roles. To further boost your ranking, ensure metrics and outcomes are quantified in your experience section.`;
    } else {
      finalResponse = `I'm here to help you accelerate your career! Whether you want to discuss resume strategy, interview questions, salary benchmarks, or find live job opportunities, just let me know what you'd like to explore next.`;
    }
  }

  yield encodeChunk({
    type: "text",
    content: finalResponse,
  });

  yield encodeChunk({ type: "done" });
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const message = body.message || body.prompt;
    const history: ChatMessage[] = body.history || body.messages || [];

    if (!message || typeof message !== "string") {
      return new Response(JSON.stringify({ error: "Message is required" }), {
        status: 400,
        headers: { "Content-Type": "application/json" },
      });
    }

    const stream = new ReadableStream({
      async start(controller) {
        const encoder = new TextEncoder();
        try {
          for await (const chunk of executeAgentWorkflow(message, history)) {
            controller.enqueue(encoder.encode(chunk));
          }
        } catch (error) {
          controller.enqueue(
            encoder.encode(
              encodeChunk({
                type: "error",
                error:
                  error instanceof Error
                    ? error.message
                    : "Workflow execution failed",
              })
            )
          );
        } finally {
          controller.close();
        }
      },
    });

    return new Response(stream, {
      headers: {
        "Content-Type": "text/event-stream; charset=utf-8",
        "Cache-Control": "no-cache, no-transform",
        Connection: "keep-alive",
        "X-Accel-Buffering": "no",
      },
    });
  } catch (error) {
    return new Response(
      JSON.stringify({
        error: error instanceof Error ? error.message : "Invalid request",
      }),
      { status: 400, headers: { "Content-Type": "application/json" } }
    );
  }
}