import secrets
import uuid
import streamlit as st
from streamlit_autorefresh import st_autorefresh
from supabase import create_client
from voice import render_voice

# ---------------- CONFIG ----------------

st.set_page_config(
    page_title="BattleVoice",
    page_icon="🎙️",
    layout="centered"
)

MAX_PLAYERS = 10

st.title("🎙️ BattleVoice")
st.caption("Private voice rooms for your Minecraft friends")


# ---------------- SUPABASE ----------------

@st.cache_resource
def get_supabase():
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_SERVICE_KEY"]
    )


try:
    supabase = get_supabase()
except Exception as e:
    st.error("Supabase connection failed.")
    st.code(str(e))
    st.stop()


# ---------------- SESSION STATE ----------------

defaults = {
    "my_token": None,
    "my_role": None,
    "my_name": None,
    "room_code": None,
}

for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


# ---------------- HELPERS ----------------

def rpc_result(name, params=None):
    return supabase.rpc(name, params or {}).execute().data


def get_room():
    result = (
        supabase.table("rooms")
        .select("*")
        .eq("id", 1)
        .execute()
    )
    return result.data[0] if result.data else None


def get_players():
    result = (
        supabase.table("room_players")
        .select("*")
        .eq("room_id", 1)
        .order("created_at")
        .execute()
    )
    return result.data


def reset_session():
    for key in defaults:
        st.session_state[key] = None
    st.rerun()


def save_identity(token, role, name, code):
    st.session_state.my_token = token
    st.session_state.my_role = role
    st.session_state.my_name = name
    st.session_state.room_code = code


def cleanup_expired_room():
    try:
        rpc_result("cleanup_battle_room")
    except Exception:
        pass


# ---------------- AUTOMATIC REFRESH ----------------

st_autorefresh(
    interval=5000,
    key="battlevoice_live_refresh"
)


# ---------------- CLEANUP ----------------

cleanup_expired_room()


# ---------------- HOME SCREEN ----------------

if st.session_state.my_token is None:

    room = get_room()

    create_tab, join_tab = st.tabs(
        ["➕ Create Room", "🚪 Join Room"]
    )

    with create_tab:
        st.subheader("Create a room")

        host_name = st.text_input(
            "Your name",
            max_chars=20,
            key="host_name"
        )

        if st.button("Create Room", use_container_width=True):
            if not host_name.strip():
                st.warning("Enter your name.")
            elif room is not None:
                st.error("A room is already active.")
            else:
                code = str(secrets.randbelow(10**10)).zfill(10)
                token = str(uuid.uuid4())

                try:
                    result = rpc_result(
                        "create_battle_room",
                        {
                            "p_code": code,
                            "p_host_name": host_name.strip(),
                            "p_host_token": token
                        }
                    )

                    if result is True:
                        save_identity(token, "host", host_name.strip(), code)
                        st.rerun()
                    else:
                        st.error(f"Could not create room: {result}")
                except Exception as e:
                    st.error("Room creation failed.")
                    st.code(str(e))

    with join_tab:
        st.subheader("Join a room — no host approval needed")

        player_name = st.text_input(
            "Your name",
            max_chars=20,
            key="join_name"
        )

        code_input = st.text_input(
            "10-digit room code",
            max_chars=10,
            key="join_code"
        )

        if st.button("Join Room", use_container_width=True):
            if not player_name.strip():
                st.warning("Enter your name.")
            elif not code_input.isdigit() or len(code_input) != 10:
                st.warning("Enter a valid 10-digit room code.")
            else:
                token = str(uuid.uuid4())

                try:
                    result = rpc_result(
                        "request_battle_join",
                        {
                            "p_code": code_input,
                            "p_player_name": player_name.strip(),
                            "p_player_token": token
                        }
                    )

                    status = str(result).upper()

                    if "JOINED" in status:
                        save_identity(token, "player", player_name.strip(), code_input)
                        st.rerun()
                    elif "ROOM_NOT_FOUND" in status:
                        st.error("Room not found. Check the code.")
                    elif "ROOM_FULL" in status:
                        st.error("Room is full (maximum 10 players).")
                    elif "NAME_TAKEN" in status:
                        st.error("That name is already taken in this room.")
                    else:
                        st.error(f"Could not join: {result}")
                except Exception as e:
                    st.error("Joining room failed.")
                    st.code(str(e))


# ---------------- ROOM SCREEN ----------------

else:
    room = get_room()

    if room is None or room["room_code"] != st.session_state.room_code:
        st.error("This room has expired or been closed.")
        if st.button("Return Home"):
            reset_session()
        st.stop()

    # Host heartbeat keeps the room alive while the host is here.
    if st.session_state.my_role == "host":
        try:
            heartbeat = rpc_result(
                "heartbeat_battle_room",
                {"p_host_token": st.session_state.my_token}
            )
            if heartbeat is not True:
                st.warning("Room heartbeat failed.")
        except Exception as e:
            st.error("Could not send room heartbeat.")
            st.code(str(e))

    players = get_players()
    my_player = next(
        (p for p in players if p["player_token"] == st.session_state.my_token),
        None
    )

    if my_player is None:
        st.error("Your room session is invalid.")
        if st.button("Return Home"):
            reset_session()
        st.stop()

    st.divider()
    st.subheader("🏠 Your Room")
    st.code(room["room_code"])
    st.write(f"**Your name:** {st.session_state.my_name}")

    if my_player["status"] == "host":
        st.success("👑 You are the host.")
    elif my_player["status"] == "approved":
        st.success("🟢 You are in the room!")
    else:
        st.error("Your room status is not valid. Please return home and join again.")
        if st.button("Return Home"):
            reset_session()
        st.stop()

    st.subheader(f"Players ({len(players)}/{MAX_PLAYERS})")
    for player in players:
        if player["status"] == "host":
            st.write(f"👑 {player['player_name']} — Host")
        elif player["status"] == "approved":
            st.write(f"🟢 {player['player_name']} — Joined")

    if st.session_state.my_role == "host":
        st.divider()
        if st.button("❌ Close Room", type="primary"):
            try:
                result = rpc_result(
                    "close_battle_room",
                    {"p_host_token": st.session_state.my_token}
                )
                if result is True:
                    reset_session()
                else:
                    st.error(f"Could not close room: {result}")
            except Exception as e:
                st.error("Closing room failed.")
                st.code(str(e))

    if my_player["status"] in ["host", "approved"]:
        st.divider()
        st.subheader("🎙️ Voice Chat")
        render_voice(st.session_state.my_token, st.session_state.my_name)

    st.caption("BattleVoice — Live Room Edition")
