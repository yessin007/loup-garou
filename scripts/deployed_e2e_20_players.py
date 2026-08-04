#!/usr/bin/env python3
"""Concurrent deployed smoke test for a 20-player Loup Garou game."""

from __future__ import annotations

import argparse
import concurrent.futures
import http.cookiejar
import json
import os
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROLE_KEYS = [
    "simple_wolves", "infecting_fathers", "cerberus_wolves", "black_wolves",
    "talkative_wolves", "blue_wolves", "white_wolves", "barbers", "aliens",
    "pyromaniacs", "prostitutes", "servants", "ancients", "hunters",
    "red_riding_hoods", "bears", "shepherds", "cupids", "judges",
    "wild_children", "angels", "ankous", "little_girls", "seers", "witches",
    "protectors", "villagers",
]

COMPOSITION = {role: 0 for role in ROLE_KEYS}
COMPOSITION.update({
    "simple_wolves": 1,
    "infecting_fathers": 1,
    "cerberus_wolves": 1,
    "black_wolves": 1,
    "barbers": 1,
    "aliens": 1,
    "prostitutes": 1,
    "servants": 1,
    "ancients": 1,
    "hunters": 1,
    "red_riding_hoods": 1,
    "bears": 1,
    "shepherds": 1,
    "cupids": 1,
    "judges": 1,
    "wild_children": 1,
    "seers": 1,
    "witches": 1,
    "protectors": 1,
    "villagers": 1,
})


class RunLog:
    def __init__(self, path: Path, append: bool = False):
        self.path = path
        self.lock = threading.Lock()
        path.parent.mkdir(parents=True, exist_ok=True)
        if not append:
            path.write_text("", encoding="utf-8")

    def write(self, event: str, **details):
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **details,
        }
        line = json.dumps(record, ensure_ascii=False, sort_keys=True)
        with self.lock:
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")
        print(line, flush=True)


class WebSession:
    def __init__(self, base_url: str, log: RunLog, actor: str):
        self.base_url = base_url.rstrip("/")
        self.log = log
        self.actor = actor
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.cookies))

    def csrf_cookie(self):
        return next((cookie.value for cookie in self.cookies if cookie.name == "csrftoken"), "")

    def request(self, method: str, path: str, *, form=None, payload=None, referer=None, label=None):
        url = path if path.startswith("http") else f"{self.base_url}{path}"
        headers = {"User-Agent": "loup-garou-e2e/1.0", "Accept": "*/*"}
        data = None
        if referer:
            headers["Referer"] = referer if referer.startswith("http") else f"{self.base_url}{referer}"
        if form is not None:
            data = urllib.parse.urlencode(form).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        elif payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        if method != "GET":
            headers["X-CSRFToken"] = self.csrf_cookie()
        started = time.monotonic()
        request = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self.opener.open(request, timeout=45) as response:
                body = response.read()
                status = response.status
                final_url = response.geturl()
        except urllib.error.HTTPError as error:
            body = error.read()
            status = error.code
            final_url = error.geturl()
        elapsed_ms = round((time.monotonic() - started) * 1000, 1)
        self.log.write(
            "http",
            actor=self.actor,
            label=label or path,
            method=method,
            status=status,
            elapsed_ms=elapsed_ms,
            final_url=final_url,
            response_bytes=len(body),
        )
        return status, final_url, body

    def get_csrf_form(self, path: str):
        status, _, body = self.request("GET", path, label=f"csrf:{path}")
        if status != 200:
            raise RuntimeError(f"{self.actor}: GET {path} returned {status}")
        match = re.search(rb'name="csrfmiddlewaretoken" value="([^"]+)"', body)
        if not match:
            raise RuntimeError(f"{self.actor}: CSRF form token missing at {path}")
        return match.group(1).decode()


def login_narrator(session: WebSession, username: str, password: str):
    token = session.get_csrf_form("/")
    status, final_url, body = session.request(
        "POST", "/",
        form={"csrfmiddlewaretoken": token, "username": username, "password": password},
        referer="/", label="narrator_login",
    )
    if status != 200 or not final_url.endswith("/accueil/"):
        raise RuntimeError(f"Narrator login failed: {status} {final_url} {body[:160]!r}")


def login_player(base_url: str, log: RunLog, username: str, password: str):
    session = WebSession(base_url, log, username)
    token = session.get_csrf_form("/")
    status, final_url, _ = session.request(
        "POST", "/",
        form={"csrfmiddlewaretoken": token, "username": username, "password": password},
        referer="/", label="player_login",
    )
    return session if status == 200 and final_url.endswith("/room/") else None


def ensure_player(base_url: str, log: RunLog, username: str, password: str):
    for attempt in range(1, 7):
        try:
            session = login_player(base_url, log, username, password)
        except RuntimeError as error:
            session = None
            log.write("login_retry_needed", actor=username, attempt=attempt, error=str(error))
        if session:
            return session
        if attempt == 1:
            try:
                return register_player(base_url, log, username, password)
            except RuntimeError as error:
                log.write("registration_recovery_needed", actor=username, error=str(error))
        time.sleep(attempt)
    raise RuntimeError(f"{username}: could not log in or recover account")


def create_room(session: WebSession):
    token = session.get_csrf_form("/accueil/?mode=new")
    form = {"csrfmiddlewaretoken": token, "player_count": "20", **{key: str(value) for key, value in COMPOSITION.items()}}
    status, final_url, body = session.request(
        "POST", "/accueil/?mode=new", form=form, referer="/accueil/?mode=new", label="create_room",
    )
    match = re.search(rb'const roomCode = "(\d{6})"', body)
    if status != 200 or not final_url.endswith("/partie/") or not match:
        raise RuntimeError(f"Room creation failed: {status} {final_url} {body[:200]!r}")
    return match.group(1).decode()


def resume_room(session: WebSession, room_code: str):
    token = session.get_csrf_form("/accueil/?mode=resume")
    status, final_url, body = session.request(
        "POST", "/accueil/?mode=resume",
        form={"csrfmiddlewaretoken": token, "action": "resume", "room_code": room_code},
        referer="/accueil/?mode=resume", label="resume_room",
    )
    if status != 200 or not final_url.endswith("/partie/"):
        raise RuntimeError(f"Room resume failed: {status} {final_url} {body[:180]!r}")


def register_player(base_url: str, log: RunLog, username: str, password: str):
    session = WebSession(base_url, log, username)
    token = session.get_csrf_form("/inscription/")
    status, final_url, body = session.request(
        "POST", "/inscription/",
        form={
            "csrfmiddlewaretoken": token,
            "username": username,
            "password": password,
            "password_confirmation": password,
        },
        referer="/inscription/", label="register",
    )
    if status != 200 or not final_url.endswith("/room/"):
        raise RuntimeError(f"{username}: registration failed: {status} {final_url} {body[:160]!r}")
    return session


def join_room(session: WebSession, room_code: str):
    for attempt in range(1, 9):
        token = session.get_csrf_form("/room/")
        status, final_url, body = session.request(
            "POST", "/room/",
            form={"csrfmiddlewaretoken": token, "room_code": room_code},
            referer="/room/", label=f"join_room_attempt_{attempt}",
        )
        if status == 200 and final_url.endswith(f"/room/{room_code}/"):
            return attempt
        if status == 503:
            time.sleep(min(0.35 * attempt, 2.0))
            continue
        raise RuntimeError(f"{session.actor}: join failed: {status} {final_url} {body[:180]!r}")
    raise RuntimeError(f"{session.actor}: join exhausted retries")


def api_json(session: WebSession, method: str, path: str, *, payload=None, label=None):
    status, final_url, body = session.request(method, path, payload=payload, referer="/partie/", label=label)
    try:
        decoded = json.loads(body)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"{session.actor}: non-JSON response from {path}: {status} {body[:180]!r}") from error
    if status < 200 or status >= 300:
        raise RuntimeError(f"{session.actor}: API {path} failed: {status} {final_url} {decoded}")
    return decoded


def player_by_role(players, role):
    return next(item for item in players if item["role"] == role)


def build_base_state(players):
    return {
        "stage": "roles", "round": 1, "eventRound": None,
        "players": players, "deaths": [], "winner": None,
        "distributionStarted": True, "roomStarted": True,
        "hunterShotRecords": [], "hunterCausedDeathIds": [],
        "alienDeathIds": [], "barberDeathIds": [], "voteDeathIds": [],
        "coupleIds": [], "qualifiers": [], "voteBreakdown": {"normal": [], "cancelled": [], "secret": [], "totals": []},
        "protectedId": None, "wolfTargetId": None, "wolfResolvedTargetId": None,
        "blockedPlayerId": None, "prostituteTargetId": None,
        "pyromaniacAction": None, "pyromaniacDousedIds": [], "pyromaniacIgnitedIds": [], "pyromaniacOiledIds": [],
        "infectionAttempted": False, "infectionSucceeded": False, "infectedPlayerId": None,
        "whiteWolfTargetId": None, "silencedPlayerId": None, "talkativePlayerId": None, "assignedWord": "",
        "witchSave": False, "witchKillId": None, "bearGrowled": None,
        "shepherdLastResults": [], "sheepRemaining": 3, "shepherdWasBlocked": False,
        "judgeFirstId": None, "judgeSecondId": None, "judgeSameClan": None,
        "seerTargetId": None, "seerDisplayedRole": None,
        "speakerId": None, "lastVote": None, "voteOutcome": None,
        "barberPlayerId": None, "barberTargetId": None, "barberHit": None,
        "alienLastGuessCorrect": None, "alienLastGuessResults": [],
        "lostVillagePowerIds": [],
    }


def reset_phase_fields(state):
    state.update({
        "deaths": [], "hunterShotRecords": [], "hunterCausedDeathIds": [],
        "alienDeathIds": [], "barberDeathIds": [], "voteDeathIds": [],
        "qualifiers": [], "voteBreakdown": {"normal": [], "cancelled": [], "secret": [], "totals": []},
        "protectedId": None, "wolfTargetId": None, "wolfResolvedTargetId": None,
        "blockedPlayerId": None, "prostituteTargetId": None,
        "witchSave": False, "witchKillId": None, "bearGrowled": None,
        "seerTargetId": None, "seerDisplayedRole": None, "speakerId": None,
        "lastVote": None, "voteOutcome": None, "barberPlayerId": None,
        "barberTargetId": None, "barberHit": None,
        "alienLastGuessCorrect": None, "alienLastGuessResults": [],
    })


def kill(players_by_role, *roles):
    victims = []
    for role in roles:
        item = players_by_role[role]
        item["alive"] = False
        victims.append(item)
    return victims


def sync_scenario(narrator, room_code, state, log, label):
    api_json(narrator, "POST", f"/api/rooms/{room_code}/sync/", payload=state, label=label)
    log.write("scenario_synced", scenario=label, stage=state["stage"], round=state["round"], alive=sum(item["alive"] for item in state["players"]), winner=state.get("winner"))


def play_scenarios(narrator, room_code, players, log):
    by_role = {item["role"]: item for item in players}
    state = build_base_state(players)

    hunter, bear = kill(by_role, "hunters", "bears")
    state.update({
        "stage": "dawn", "round": 1, "eventRound": 1,
        "deaths": [hunter["id"]], "wolfTargetId": hunter["id"],
        "blockedPlayerId": by_role["seers"]["id"], "bearGrowled": True,
        "hunterShotRecords": [{"hunterId": hunter["id"], "targetId": bear["id"], "deathIds": [bear["id"]], "source": "night"}],
    })
    sync_scenario(narrator, room_code, state, log, "night_1_hunter_chain")

    reset_phase_fields(state)
    wolf, seer = kill(by_role, "infecting_fathers", "seers")
    state.update({
        "stage": "day_end", "round": 1, "eventRound": 1, "voteOutcome": "skipped",
        "speakerId": by_role["cerberus_wolves"]["id"],
        "barberPlayerId": by_role["barbers"]["id"], "barberTargetId": wolf["id"], "barberHit": True,
        "barberDeathIds": [wolf["id"]], "alienDeathIds": [seer["id"]],
        "alienLastGuessCorrect": True,
        "alienLastGuessResults": [{"id": seer["id"], "guessedRole": "seers", "correct": True}],
    })
    sync_scenario(narrator, room_code, state, log, "day_1_barber_alien_skip")

    reset_phase_fields(state)
    witch, alien = kill(by_role, "witches", "aliens")
    state.update({
        "stage": "dawn", "round": 2, "eventRound": 2,
        "deaths": [witch["id"], alien["id"]], "wolfTargetId": witch["id"], "witchKillId": alien["id"],
    })
    sync_scenario(narrator, room_code, state, log, "night_2_wolves_and_witch")

    reset_phase_fields(state)
    shepherd = kill(by_role, "shepherds")[0]
    state.update({
        "stage": "day_end", "round": 2, "eventRound": 2,
        "lastVote": shepherd["id"], "voteDeathIds": [shepherd["id"]], "voteOutcome": "eliminated",
        "qualifiers": [shepherd["id"]],
        "voteBreakdown": {"normal": [{"targetId": shepherd["id"], "votes": 7}], "cancelled": [], "secret": [], "totals": [{"id": shepherd["id"], "votes": 7}]},
    })
    sync_scenario(narrator, room_code, state, log, "day_2_vote_elimination")

    reset_phase_fields(state)
    state.update({
        "stage": "dawn", "round": 3, "eventRound": 3,
        "protectedId": by_role["villagers"]["id"], "wolfTargetId": by_role["villagers"]["id"],
    })
    sync_scenario(narrator, room_code, state, log, "night_3_protected_no_death")

    reset_phase_fields(state)
    state.update({"stage": "day_end", "round": 3, "eventRound": 3, "voteOutcome": "tie"})
    sync_scenario(narrator, room_code, state, log, "day_3_tie")

    schedule = [
        (4, "villagers", "black_wolves"),
        (5, "protectors", "servants"),
        (6, "red_riding_hoods", "wild_children"),
        (7, "cupids", "judges"),
    ]
    for round_number, night_role, day_role in schedule:
        reset_phase_fields(state)
        night_victim = kill(by_role, night_role)[0]
        state.update({
            "stage": "dawn", "round": round_number, "eventRound": round_number,
            "deaths": [night_victim["id"]], "wolfTargetId": night_victim["id"],
        })
        sync_scenario(narrator, room_code, state, log, f"night_{round_number}_wolves_kill_{night_role}")

        reset_phase_fields(state)
        day_victim = kill(by_role, day_role)[0]
        state.update({
            "stage": "day_end", "round": round_number, "eventRound": round_number,
            "lastVote": day_victim["id"], "voteDeathIds": [day_victim["id"]], "voteOutcome": "eliminated",
            "qualifiers": [day_victim["id"]],
        })
        sync_scenario(narrator, room_code, state, log, f"day_{round_number}_vote_{day_role}")

    reset_phase_fields(state)
    prostitute = kill(by_role, "prostitutes")[0]
    state.update({
        "stage": "dawn", "round": 8, "eventRound": 8, "deaths": [prostitute["id"]],
        "wolfTargetId": prostitute["id"], "winner": "wolves",
    })
    sync_scenario(narrator, room_code, state, log, "night_8_wolves_parity_win")
    state["stage"] = "game_over"
    sync_scenario(narrator, room_code, state, log, "game_over_wolves")
    return state


def validate_history(history, expected_room_status, log):
    errors = []
    events = history.get("events", [])
    if history.get("status") != expected_room_status:
        errors.append(f"status={history.get('status')} expected={expected_room_status}")
    if len(events) != 15:
        errors.append(f"event_count={len(events)} expected=15")
    markers = [(event.get("type"), event.get("round")) for event in events]
    if len(markers) != len(set(markers)):
        errors.append("duplicate night/day markers")
    by_marker = {(event["type"], event["round"]): event.get("details", {}) for event in events}
    night1 = by_marker.get(("night", 1), {})
    if len(night1.get("deaths", [])) != 2 or len(night1.get("hunter_deaths", [])) != 1:
        errors.append(f"night1 hunter/deaths mismatch: {night1.get('deaths')} / {night1.get('hunter_deaths')}")
    day2 = by_marker.get(("day", 2), {})
    if day2.get("barber_target") or day2.get("alien_guesses"):
        errors.append("day2 contains stale Barber/Alien actions")
    night3 = by_marker.get(("night", 3), {})
    if night3.get("deaths"):
        errors.append(f"protected night recorded deaths: {night3.get('deaths')}")
    last = events[-1].get("details", {}) if events else {}
    if last.get("winner") != "wolves":
        errors.append(f"final winner={last.get('winner')} expected=wolves")
    log.write("history_validation", ok=not errors, errors=errors, status=history.get("status"), event_count=len(events), markers=markers)
    return errors


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="https://loup-garou-67d2.onrender.com")
    parser.add_argument("--log", required=True)
    parser.add_argument("--resume-run-id")
    parser.add_argument("--room-code")
    args = parser.parse_args()
    narrator_password = os.environ.get("LOADTEST_NARRATOR_PASSWORD")
    if not narrator_password:
        raise SystemExit("LOADTEST_NARRATOR_PASSWORD is required")

    if bool(args.resume_run_id) != bool(args.room_code):
        raise SystemExit("--resume-run-id and --room-code must be provided together")
    log = RunLog(Path(args.log), append=bool(args.room_code))
    run_id = args.resume_run_id or datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    player_password = f"E2e-{run_id}!"
    usernames = [f"e2e20_{run_id}_{index:02d}" for index in range(1, 21)]
    log.write("run_resumed" if args.room_code else "run_started", base_url=args.base_url, run_id=run_id, player_count=20, usernames=usernames, room_code=args.room_code)

    narrator = WebSession(args.base_url, log, "narrator:yessin")
    login_narrator(narrator, "yessin", narrator_password)
    if args.room_code:
        room_code = args.room_code
        resume_room(narrator, room_code)
    else:
        room_code = create_room(narrator)
        log.write("room_created", room_code=room_code, composition=COMPOSITION)

    sessions = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        account_task = ensure_player if args.room_code else register_player
        futures = {executor.submit(account_task, args.base_url, log, username, player_password): username for username in usernames}
        for future in concurrent.futures.as_completed(futures):
            username = futures[future]
            sessions[username] = future.result()
    log.write("parallel_login_complete" if args.room_code else "parallel_registration_complete", successful=len(sessions))

    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = {executor.submit(join_room, session, room_code): username for username, session in sessions.items()}
        join_attempts = {futures[future]: future.result() for future in concurrent.futures.as_completed(futures)}
    log.write("parallel_join_complete", successful=len(join_attempts), attempts=join_attempts)

    lobby = api_json(narrator, "GET", f"/api/rooms/{room_code}/lobby/", label="lobby_after_joins")
    if lobby.get("registered_count") != 20:
        raise RuntimeError(f"Lobby has {lobby.get('registered_count')} players, expected 20")
    distribution = api_json(narrator, "POST", f"/api/rooms/{room_code}/start/", payload={}, label="start_distribution")
    assignments = distribution.get("assignments", [])
    if len(assignments) != 20 or distribution.get("remaining_roles"):
        raise RuntimeError(f"Distribution mismatch: assignments={len(assignments)}, remaining={distribution.get('remaining_roles')}")
    log.write("distribution_complete", assignments=assignments)

    expected_roles = {item["name"]: item["role"] for item in assignments}
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        futures = {
            executor.submit(api_json, session, "GET", f"/api/rooms/{room_code}/player/", label="fetch_role"): username
            for username, session in sessions.items()
        }
        role_payloads = {futures[future]: future.result() for future in concurrent.futures.as_completed(futures)}
    role_errors = [
        f"{username}: got={payload.get('role', {}).get('code')} expected={expected_roles.get(username)}"
        for username, payload in role_payloads.items()
        if (payload.get("role") or {}).get("code") != expected_roles.get(username)
    ]
    log.write("parallel_role_fetch_complete", successful=20 - len(role_errors), errors=role_errors, roles={name: payload.get("role") for name, payload in role_payloads.items()})
    if role_errors:
        raise RuntimeError("Role verification failed: " + "; ".join(role_errors))

    players = [
        {"id": index, "roomPlayerId": item["room_player_id"], "name": item["name"], "role": item["role"], "alive": True}
        for index, item in enumerate(assignments, 1)
    ]
    final_state = play_scenarios(narrator, room_code, players, log)
    history = api_json(narrator, "GET", f"/api/rooms/{room_code}/history/", label="fetch_final_history")
    log.write("history_payload", room_code=room_code, history=history)
    errors = validate_history(history, "finished", log)
    log.write(
        "run_complete", ok=not errors, room_code=room_code,
        final_alive=[{"name": item["name"], "role": item["role"]} for item in final_state["players"] if item["alive"]],
        validation_errors=errors,
    )
    print(json.dumps({"ok": not errors, "room_code": room_code, "log": str(Path(args.log).resolve()), "errors": errors}, ensure_ascii=False))
    return 0 if not errors else 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"FATAL: {error}", file=sys.stderr)
        raise
