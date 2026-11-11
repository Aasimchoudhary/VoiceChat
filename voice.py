
import json
import streamlit as st
import streamlit.components.v1 as components


def render_voice(player_token, player_name):

    supabase_url = st.secrets["SUPABASE_URL"]
    anon_key = st.secrets["SUPABASE_ANON_KEY"]

    peer_host = st.secrets.get("PEER_HOST", "localhost")
    peer_port = int(st.secrets.get("PEER_PORT", 9000))
    peer_path = st.secrets.get("PEER_PATH", "/battlevoice")

    config = {
        "supabaseUrl": supabase_url,
        "anonKey": anon_key,
        "token": player_token,
        "name": player_name,
        "peerHost": peer_host,
        "peerPort": peer_port,
        "peerPath": peer_path,
    }

    config_json = json.dumps(config)

    html = """
    <div id="app" style="font-family:Arial;color:#e8eefc;background:#101b32;padding:18px;border-radius:14px;">
      <h2>🎙️ BattleVoice — Voice Chat</h2>
      <p id="status">Not connected to voice.</p>

      <button id="join" style="padding:12px;background:#2563eb;color:white;border:0;border-radius:8px;">
        🎤 Join Voice
      </button>

      <button id="mute" disabled style="padding:12px;background:#475569;color:white;border:0;border-radius:8px;">
        🔇 Mute
      </button>

      <button id="leave" disabled style="padding:12px;background:#dc2626;color:white;border:0;border-radius:8px;">
        🚪 Leave Voice
      </button>

      <h3>Connected players</h3>
      <div id="players">Nobody connected yet.</div>
      <div id="audio"></div>
    </div>

    <script src="https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2"></script>
    <script src="https://unpkg.com/peerjs@1.5.5/dist/peerjs.min.js"></script>

    <script>
    const CONFIG = __CONFIG__;

    const statusEl = document.getElementById("status");
    const playersEl = document.getElementById("players");
    const joinBtn = document.getElementById("join");
    const muteBtn = document.getElementById("mute");
    const leaveBtn = document.getElementById("leave");

    const db = window.supabase.createClient(
      CONFIG.supabaseUrl,
      CONFIG.anonKey
    );

    let peer = null;
    let localStream = null;
    let muted = false;
    let activeCalls = {};
    let polling = null;
    let knownPeers = new Set();

    function status(message) {
      statusEl.textContent = message;
    }

    function showPlayers(names) {
      playersEl.replaceChildren();

      if (!names.length) {
        playersEl.textContent = "Waiting for other players...";
        return;
      }

      names.forEach(name => {
        const item = document.createElement("p");
        item.textContent = "🟢 " + name;
        playersEl.appendChild(item);
      });
    }

    function attachAudio(stream, id) {
      let audio = document.getElementById("audio-" + id);

      if (!audio) {
        audio = document.createElement("audio");
        audio.id = "audio-" + id;
        audio.autoplay = true;
        audio.playsInline = true;
        document.getElementById("audio").appendChild(audio);
      }

      audio.srcObject = stream;
      audio.play().catch(() => {
        status("Audio received. If silent, interact with the page.");
      });
    }

    function handleCall(call) {
      if (activeCalls[call.peer]) return;

      activeCalls[call.peer] = call;
      call.answer(localStream);

      call.on("stream", stream => {
        attachAudio(stream, call.peer);
      });

      call.on("close", () => {
        delete activeCalls[call.peer];
        document.getElementById("audio-" + call.peer)?.remove();
      });

      call.on("error", error => {
        console.error(error);
      });
    }

    async function discoverPlayers() {
      const { data, error } = await db.rpc(
        "get_battle_peers",
        { p_player_token: CONFIG.token }
      );

      if (error) {
        status("Could not retrieve voice players: " + error.message);
        return;
      }

      const available = (data || []).filter(
        p => p.peer_id && p.peer_id !== peer.id
      );

      showPlayers(
        (data || []).map(p => p.player_name)
      );

      for (const player of available) {
        if (activeCalls[player.peer_id]) continue;
        if (knownPeers.has(player.peer_id)) continue;

        knownPeers.add(player.peer_id);

        const call = peer.call(player.peer_id, localStream);

        if (!call) {
          knownPeers.delete(player.peer_id);
          continue;
        }

        activeCalls[player.peer_id] = call;

        call.on("stream", stream => {
          attachAudio(stream, player.peer_id);
        });

        call.on("close", () => {
          delete activeCalls[player.peer_id];
          knownPeers.delete(player.peer_id);
          document.getElementById("audio-" + player.peer_id)?.remove();
        });

        call.on("error", error => {
          console.error(error);
          knownPeers.delete(player.peer_id);
        });
      }
    }

    async function joinVoice() {
      joinBtn.disabled = true;
      status("Requesting microphone permission...");

      try {
        localStream = await navigator.mediaDevices.getUserMedia({
          audio: {
            echoCancellation: true,
            noiseSuppression: true,
            autoGainControl: true
          },
          video: false
        });

        peer = new Peer(undefined, {
          host: CONFIG.peerHost,
          port: CONFIG.peerPort,
          path: CONFIG.peerPath,
          secure: window.location.protocol === "https:",
          debug: 1
        });

        peer.on("open", async id => {
          const { data, error } = await db.rpc(
            "set_battle_peer_id",
            {
              p_player_token: CONFIG.token,
              p_peer_id: id
            }
          );

          if (error || data !== true) {
            status("Could not register voice connection.");
            console.error(error);
            leaveVoice();
            return;
          }

          status("Connected to voice! 🎙️");

          muteBtn.disabled = false;
          leaveBtn.disabled = false;

          await discoverPlayers();

          polling = setInterval(discoverPlayers, 3000);
        });

        peer.on("call", handleCall);

        peer.on("error", error => {
          status("PeerJS error: " + error.type);
          console.error(error);
        });

        peer.on("disconnected", () => {
          status("Voice signaling disconnected. Reconnecting...");
          peer.reconnect();
        });

      } catch (error) {
        status("Microphone error: " + error.message);
        joinBtn.disabled = false;
      }
    }

    async function leaveVoice() {
      if (polling) clearInterval(polling);
      polling = null;

      if (peer) {
        peer.destroy();
        peer = null;
      }

      Object.values(activeCalls).forEach(call => call.close());
      activeCalls = {};
      knownPeers.clear();

      if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
        localStream = null;
      }

      await db.rpc("clear_battle_peer_id", {
        p_player_token: CONFIG.token
      });

      document.getElementById("audio").replaceChildren();

      muted = false;
      muteBtn.textContent = "🔇 Mute";
      muteBtn.disabled = true;
      leaveBtn.disabled = true;
      joinBtn.disabled = false;

      status("You left voice chat.");
      playersEl.textContent = "Nobody connected yet.";
    }

    joinBtn.addEventListener("click", joinVoice);

    muteBtn.addEventListener("click", () => {
      if (!localStream) return;

      muted = !muted;

      localStream.getAudioTracks().forEach(track => {
        track.enabled = !muted;
      });

      muteBtn.textContent = muted ? "🎤 Unmute" : "🔇 Mute";
      status(muted ? "Microphone muted." : "Microphone active.");
    });

    leaveBtn.addEventListener("click", leaveVoice);

    window.addEventListener("beforeunload", () => {
      if (localStream) {
        localStream.getTracks().forEach(track => track.stop());
      }
      if (peer) peer.destroy();
    });
    </script>
    """

    html = html.replace("__CONFIG__", config_json)

    components.html(html, height=450, scrolling=True)
