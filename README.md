# Customer Support Voice Agent

A production-ready AI-powered customer support voice agent built with **LangGraph**, **LiveKit**, **Whisper STT**, and **Kokoro TTS**.

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
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │           LangGraph Customer Support Agent                   │ │
│  │  ┌──────────┐  ┌────────────┐  ┌───────────────────────┐   │ │
│  │  │ Agent    │→ │ Tool Node  │→ │ End / Respond         │   │ │
│  │  │ (GPT-4o) │  │ (5 tools)  │  │                       │   │ │
│  │  └──────────┘  └────────────┘  └───────────────────────┘   │ │
│  └─────────────────────────────────────────────────────────────┘ │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐  │
│  │  Voice Agent Worker  │  │  Session Management              │  │
│  │  LiveKit ↔ STT ↔ AI  │  │  + LiveKit Token Service         │  │
│  │  ↔ TTS ↔ LiveKit     │  │                                  │  │
│  └──────────┬───────────┘  └──────────────────────────────────┘  │
└─────────────┼────────────────────────────────────────────────────┘
              │
    ┌─────────┼──────────┐
    │         │          │
┌───▼───┐ ┌──▼───┐ ┌────▼─────┐
│LiveKit│ │ STT  │ │   TTS    │
│Server │ │Whisper│ │  Kokoro  │
│ :7880 │ │ :8001│ │  :8002   │
└───────┘ └──────┘ └──────────┘
```

## Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18, Vite, Tailwind CSS, LiveKit Client SDK |
| Backend | FastAPI, Python 3.11 |
| AI Agent | LangGraph with GPT-4o-mini, 5 support tools |
| Voice | LiveKit Server (WebRTC SFU) |
| STT | OpenAI Whisper (self-hosted, streaming) |
| TTS | Kokoro TTS (self-hosted, streaming) |
| Infra | Docker Compose, Nginx, Redis |

## Quick Start

### 1. Clone and configure

```bash
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

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000/docs
- LiveKit: ws://localhost:7880

## LangGraph Agent Tools

The AI agent has 5 customer support tools:

| Tool | Purpose |
|------|---------|
| `lookup_order` | Check order status by order ID |
| `lookup_account` | Look up customer account by email |
| `check_knowledge_base` | Search FAQ/knowledge base |
| `create_ticket` | Escalate to human support |
| `end_call` | End the voice call |

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
├── backend/                    # FastAPI + LangGraph
│   ├── app/
│   │   ├── agent/
│   │   │   ├── graph.py        # LangGraph state graph
│   │   │   ├── tools.py        # 5 support tools
│   │   │   └── voice_worker.py # LiveKit ↔ STT ↔ Agent ↔ TTS
│   │   ├── api/
│   │   │   ├── sessions.py     # Session CRUD endpoints
│   │   │   └── health.py       # Health check
│   │   ├── core/
│   │   │   ├── config.py       # Pydantic settings
│   │   │   └── session_store.py # In-memory session store
│   │   ├── models/
│   │   │   └── schemas.py      # Pydantic schemas
│   │   ├── services/
│   │   │   └── livekit_service.py # Token + room management
│   │   └── main.py             # FastAPI entry point
│   └── config/prompts/
│       └── customer_support_prompt.yaml
│
├── frontend/                   # React Chat UI
│   └── src/
│       ├── App.jsx
│       ├── components/
│       │   ├── ChatMessage.jsx
│       │   ├── ControlBar.jsx
│       │   └── TypingIndicator.jsx
│       └── hooks/
│           └── useVoiceSession.js  # LiveKit hook
│
├── stt_service/                # Whisper STT microservice
│   └── main.py                 # HTTP + WebSocket endpoints
│
├── tts_service/                # Kokoro TTS microservice
│   └── main.py                 # Streaming synthesis
│
├── docker/                     # Dockerfiles + nginx config
├── livekit/                    # LiveKit server config
├── docker-compose.yaml         # Full stack orchestration
└── Makefile                    # Convenience commands
```

## Audio Pipeline

```
User speaks → Mic → LiveKit Room → Voice Worker
  → PCM frames buffered (VAD: energy-based)
  → Silence detected → POST to Whisper STT
  → Transcribed text → LangGraph Agent
  → Agent response → POST to Kokoro TTS (streaming)
  → PCM frames → LiveKit AudioSource → User hears
```

## Environment Variables

See `.env.example` for all configuration options. The minimum required:

- `OPENAI_API_KEY` — For the LangGraph agent LLM
- `LIVEKIT_API_KEY` / `LIVEKIT_API_SECRET` — LiveKit auth

## Extending

**Add new tools**: Edit `backend/app/agent/tools.py` and add to the `support_tools` list.

**Change LLM**: Edit `backend/app/agent/graph.py` — update `model_name` parameter.

**Change voice**: Set `KOKORO_VOICE` env var (see `GET /voices` on TTS service).

**Production**: Replace `session_store.py` with Redis-backed store, add MongoDB for persistence.
