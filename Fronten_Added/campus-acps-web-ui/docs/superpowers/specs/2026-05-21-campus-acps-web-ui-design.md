# Campus ACPs Web UI Design

## Goal

Build a local, polished web interface for the campus-life ACPs multi-agent project. The page should make the acceptance demo easy to use and easy to understand: a user chats with the leader assistant, the assistant routes work to campus partner agents, and the UI shows the call chain as the result is assembled.

The implementation should keep the existing protocol path intact. The new web service calls `leader_bridge.py`; `leader_bridge.py` continues to route to the four AIP partner services.

## Scope

In scope:

- A local web page served from `http://127.0.0.1:5000`.
- A Python web backend that proxies chat requests to `leader_bridge.py`.
- Automatic routing by lightweight intent rules.
- Manual routing through user-selected partner agents.
- A chat panel for user and assistant messages.
- A right-side call-chain panel showing each step and status.
- A left-side control panel with dispatch mode, partner choices, and service status.
- Demo prompt buttons for reliable acceptance presentation.
- Clear error states when the bridge or partner agents are unavailable.

Out of scope:

- Replacing Coze, ACPs, ADP, AIP, or mTLS behavior.
- Building a full account system, database, or persistent chat history.
- Streaming token-by-token model output.
- Directly calling partner agents from the new web backend.

## Architecture

Add a small local web app:

- `web_app.py`: starts a local web server on port `5000`.
- `web/index.html`: main page structure.
- `web/styles.css`: visual design and responsive layout.
- `web/app.js`: chat interaction, API calls, call-chain rendering, and UI state.

The backend talks to the existing leader bridge:

- `GET /` serves the page.
- `GET /api/status` checks whether `leader_bridge.py` is reachable and returns configured partner metadata.
- `POST /api/chat` accepts a user message and dispatch settings, then calls `http://127.0.0.1:8766/call` for each selected partner.

The existing runtime remains:

- `food_agent/main.py` on `8088`.
- `express_agent/main.py` on `8089`.
- `weather_agent/main.py` on `8090`.
- `date_agent/main.py` on `8091`.
- `leader_bridge.py` on `8766`.
- `web_app.py` on `5000`.

## Routing

The UI supports two modes:

- Automatic mode: the user enters a natural-language request and the backend chooses relevant partners.
- Manual mode: the user selects one partner and the backend calls only that partner.

Automatic mode uses deterministic keyword rules so the demo is predictable:

- Weather partner: weather, temperature, rain, wind, cold, hot, outfit, umbrella, weather-related Chinese terms such as `天气`, `下雨`, `温度`, `穿`, `穿搭`, `带伞`, `冷`, `热`, `刮风`.
- Express partner: express, package, logistics, tracking, pickup, Chinese terms such as `快递`, `物流`, `单号`, `取件`, `驿站`, `到哪`.
- Food partner: food, canteen, delivery, order, meal, Chinese terms such as `吃`, `外卖`, `食堂`, `菜单`, `点餐`, `下单`, `晚饭`, `午饭`.
- Date partner: date planning, restaurant, movie, relationship outing, Chinese terms such as `约会`, `餐厅`, `电影`, `规划`, `女朋友`, `男朋友`, `情侣`.

If multiple categories match, call multiple partners and aggregate their replies. If none match, return a friendly prompt asking the user to choose a scene or rephrase with one of the supported campus-life topics.

## User Interface

The page uses a three-column workbench layout:

- Left panel: product title, dispatch mode switch, partner buttons, service status.
- Center panel: chat history, demo prompts, input box, send button.
- Right panel: call chain with step status.

The first viewport should immediately communicate the product identity: `北邮个人助手` and `Campus ACPs Console`. The UI should feel like a polished operations console for a campus assistant, not a marketing landing page.

Visual direction:

- Clean, modern, academic-tech tone.
- White and light blue base with distinct accent colors per partner.
- Cards only for concrete units such as agent chips, messages, and call-chain nodes.
- No decorative gradient orbs or heavy hero treatment.
- Dense enough for demo operation, but not cluttered.

## Data Flow

1. User enters a message in the browser.
2. Frontend appends the user message and creates a pending assistant message.
3. Frontend sends `POST /api/chat`.
4. Backend determines selected partners based on mode.
5. Backend calls `leader_bridge.py /call` for each partner.
6. Backend gathers successful replies and errors.
7. Backend returns:
   - chosen partners,
   - call-chain steps,
   - combined assistant reply,
   - per-partner status and elapsed time.
8. Frontend updates the chat message and right-side call-chain panel.

## Error Handling

If `leader_bridge.py` is offline:

- `GET /api/status` returns bridge status as offline.
- The page shows a visible but non-blocking warning with the command `python leader_bridge.py`.
- `POST /api/chat` returns a clear error instead of hanging.

If a partner call fails:

- The corresponding call-chain node becomes failed.
- The assistant reply keeps successful partner results and states which partner was unavailable.

If all partner calls fail:

- The page displays a failure response with suggested startup commands.

All outbound backend calls should use timeouts to keep the UI responsive.

## Demo Prompts

Include three prompt chips:

- `下午去取快递，顺便吃饭，今天穿什么？`
- `下雨天和女朋友在学校附近约会怎么安排？`
- `帮我查快递并规划取件时间`

These prompts are designed to show single-agent and multi-agent routing during acceptance.

## Verification

Manual verification should cover:

- `web_app.py` starts successfully.
- Browser opens `http://127.0.0.1:5000`.
- `/api/status` reports bridge availability.
- Manual mode calls each of the four partners.
- Automatic mode routes to weather, express, food, date, and multi-partner combinations.
- Bridge-offline state is shown clearly.
- Partner failure state is shown clearly.
- The layout fits desktop demo screens and remains usable on narrower browser widths.

## Open Decisions

No product decisions remain open for the first implementation. Flask is acceptable for the backend. If Flask is unavailable locally, the fallback is a standard-library HTTP server with the same API shape.
