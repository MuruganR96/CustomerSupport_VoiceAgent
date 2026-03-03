# Customer Support Voice Agent

A production-ready AI-powered customer support voice agent built with **LiveKit Agents**, **LangGraph**, **FasterWhisper STT**, and **Kokoro TTS**.

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        Frontend (React)                          │
│  Chat UI · LiveKit Client · Mic/Audio · Transcription Display    │
│                     Port 3000 (Nginx)                            │
└─────────────────────────┬────────────────────────────────────────┘
                          │ REST API + WebSocket
┌─────────────────────────▼────────────────────────────────────────┐
│                   Backend (FastAPI)  :8000                        │
│  Session Management · LiveKit Token Service · Health Check        │
└─────────────────────────┬────────────────────────────────────────┘
                          │
┌─────────────────────────▼────────────────────────────────────────┐
│                Agent Worker (LiveKit Agents)                      │
│  ┌──────────────────────────────────────────────────────────────┐│
│  │              LangGraph Customer Support Agent                ││
│  │   ┌──────────┐   ┌────────────┐   ┌──────────────────┐      ││
│  │   │ Agent    │ → │ Tool Node  │ → │ End / Respond    │      ││
│  │   │(GPT-4o)  │   │ (5 tools)  │   │                  │      ││
│  │   └──────────┘   └────────────┘   └──────────────────┘      ││
│  └──────────────────────────────────────────────────────────────┘│
│  ┌─────────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ FasterWhisper   │  │ Silero VAD   │  │ Kokoro TTS         │  │
│  │ STT (in-proc)   │  │              │  │ (in-proc)          │  │
│  └─────────────────┘  └──────────────┘  └────────────────────┘  │
└─────────────────────────┬────────────────────────────────────────┘
                          │
                ┌─────────▼──────────┐
                │   LiveKit Server   │
                │    :7880 (SFU)     │
                └────────────────────┘
```

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Vite, Pure CSS (vm- design system), LiveKit Client SDK |
| Backend | FastAPI, Python 3.11, LiveKit Server SDK |
| AI Agent | LangGraph + GPT-4o-mini, 5 support tools |
| Voice Pipeline | LiveKit Agents framework (AgentSession, VoicePipelineAgent) |
| STT | FasterWhisper (self-hosted, in-process plugin) |
| TTS | Kokoro TTS (self-hosted, in-process plugin) |
| VAD | Silero VAD |
| Infra | Docker Compose, Nginx, Redis |

## Quick Start

### 1. Clone and configure

```bash
git clone <your-repo-url>
cd CustmerSupport_VoiceAgent

cp .env.example .env
# Edit .env with your OpenAI API key
```

### 2. Start with Docker Compose

```bash
# Build and start all services
docker compose up -d --build

# Watch logs
docker compose logs -f
```

### 3. Open the app

- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000/docs
- **LiveKit**: ws://localhost:7880

## How It Works

1. User opens the frontend and clicks **Connect Now**
2. Backend creates a session and returns a LiveKit token
3. Frontend connects to LiveKit room, enables microphone
4. Agent Worker joins the room via LiveKit Agents framework
5. User speaks → Silero VAD detects speech → FasterWhisper transcribes
6. Transcription → LangGraph agent reasons and calls tools if needed
7. Agent response → Kokoro TTS synthesizes speech → User hears reply
8. Transcriptions appear in the chat UI in real-time (word-by-word accumulation)

## LangGraph Agent Tools

The AI agent has 5 customer support tools:

| Tool | Purpose |
|------|---------|
| `lookup_order` | Check order status by order ID |
| `lookup_account` | Look up customer account by email |
| `check_knowledge_base` | Search FAQ/knowledge base |
| `create_ticket` | Escalate to human support |
| `end_call` | End the voice call |

## Frontend UI

The chat-centric UI uses a custom `vm-` CSS design system (no Tailwind):

- **Pre-join screen**: Name input + Connect Now button
- **Active call**: Scrollable chat with gray agent bubbles (left) and gradient user bubbles (right)
- **Typing indicator**: Three bouncing dots when agent is thinking
- **Speaking pill**: Floating indicator for "Agent is speaking..." / "Listening..."
- **Input bar**: Text input + mic toggle (with pulse animation) + End call button
- **End screen**: Call complete summary with duration
- **Responsive**: 560px centered card on desktop, full-width on mobile

## Makefile Commands

```bash
make help          # Show all commands
make build         # Build Docker images
make up            # Start services
make down          # Stop services
make logs          # Follow all logs
make logs-backend  # Follow backend logs only
make dev-backend   # Run backend locally
make dev-frontend  # Run frontend locally
```

## Project Structure

```
├── agent_worker/              # LiveKit Agents voice worker
│   ├── main.py                # Worker entrypoint (AgentSession)
│   ├── agent/
│   │   ├── graph.py           # LangGraph state graph + prompt
│   │   └── tools.py           # 5 support tools
│   ├── config/prompts/
│   │   └── customer_support_prompt.yaml
│   └── plugins/
│       ├── faster_whisper_stt.py  # In-process STT plugin
│       └── kokoro_tts.py          # In-process TTS plugin
│
├── backend/                   # FastAPI session management
│   ├── app/
│   │   ├── main.py            # FastAPI entry point
│   │   ├── api/
│   │   │   ├── sessions.py    # Session CRUD endpoints
│   │   │   └── health.py      # Health check
│   │   ├── core/
│   │   │   ├── config.py      # Pydantic settings
│   │   │   └── session_store.py
│   │   ├── models/
│   │   │   └── schemas.py     # Pydantic schemas
│   │   └── services/
│   │       └── livekit_service.py  # Token + room management
│   └── config/prompts/
│       └── customer_support_prompt.yaml
│
├── frontend/                  # React chat UI
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── App.jsx            # Main layout (3 states)
│       ├── main.jsx
│       ├── components/
│       │   └── ChatMessage.jsx    # Message bubbles
│       ├── hooks/
│       │   └── useVoiceSession.js # LiveKit room hook
│       └── styles/
│           └── index.css          # vm- design system
│
├── docker/                    # Dockerfiles + nginx config
│   ├── Dockerfile.agent
│   ├── Dockerfile.backend
│   ├── Dockerfile.frontend
│   └── nginx.conf
│
├── livekit/                   # LiveKit server config
│   └── livekit.yaml
│
├── docker-compose.yaml        # Full stack orchestration
├── Makefile                   # Convenience commands
├── .env.example               # Environment template
└── .gitignore
```

## Audio Pipeline

```
User speaks → Mic → LiveKit Room → Agent Worker
  → Silero VAD detects speech boundaries
  → Audio frames → FasterWhisper STT (in-process)
  → Transcribed text → LangGraph Agent (reason + tools)
  → Agent response text → Kokoro TTS (in-process, streaming)
  → Audio frames → LiveKit AudioSource → User hears reply
```

## Environment Variables

See `.env.example` for all configuration options. The minimum required:

- `OPENAI_API_KEY` — For the LangGraph agent LLM
- `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` — LiveKit auth (defaults: `devkey`/`secret`)

## Extending

**Add new tools**: Edit `agent_worker/agent/tools.py` and add to the `support_tools` list.

**Change LLM**: Edit `agent_worker/agent/graph.py` — update `model_name` parameter in `create_agent_graph()`.

**Change voice**: Set `KOKORO_VOICE` env var (default: `af_heart`).

**Change STT model**: Set `WHISPER_MODEL` env var (default: `base`, options: `tiny`, `base`, `small`, `medium`, `large-v3`).

**Production**: Replace `session_store.py` with Redis-backed store, add persistent database for session history.
