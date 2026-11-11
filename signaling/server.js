
const { PeerServer } = require("peer");

const PORT = process.env.PORT || 9000;

const server = PeerServer({
    port: PORT,
    path: "/battlevoice",
    proxied: true
});

server.on("connection", (client) => {
    console.log("Player connected:", client.getId());
});

server.on("disconnect", (client) => {
    console.log("Player disconnected:", client.getId());
});

console.log(`BattleVoice PeerServer running on port ${PORT}`);
