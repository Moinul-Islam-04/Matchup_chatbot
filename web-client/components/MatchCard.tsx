/* eslint-disable @next/next/no-img-element */
import { lookupIcon, type IconMaps } from "@/lib/ddragon";

export type MatchPlayer = {
  champion: string;
  riotId: string;
  isJungle: boolean;
  isYou: boolean;
  rank: string | null;
};
export type MatchTeam = { side: string; players: MatchPlayer[] };
export type MatchData = {
  queue: string;
  gameLengthSec: number;
  teams: MatchTeam[];
  bans: string[];
};

function mmss(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, "0")}`;
}

function Champ({ name, icons }: { name: string; icons: IconMaps | null }) {
  const url = lookupIcon(icons, name);
  return url ? (
    <img className="mc-champ-icon" src={url} alt={name} title={name} />
  ) : (
    <span className="mc-champ-icon mc-placeholder" />
  );
}

export function MatchCard({
  match,
  icons,
}: {
  match: MatchData;
  icons: IconMaps | null;
}) {
  return (
    <div className="mc-card">
      <div className="mc-header">
        <span className="gold">● Live Match</span>
        <span className="mc-meta">
          {match.queue} · {mmss(match.gameLengthSec)}
        </span>
      </div>

      <div className="mc-teams">
        {match.teams.map((team, i) => {
          const isRed = team.side.toLowerCase().includes("red");
          return (
            <div className="mc-team" key={i}>
              <div className={`mc-team-title ${isRed ? "red" : "blue"}`}>
                {team.side}
              </div>
              {team.players.map((p, j) => (
                <div className={`mc-player${p.isYou ? " you" : ""}`} key={j}>
                  <Champ name={p.champion} icons={icons} />
                  <div className="mc-main">
                    <span className="mc-name">
                      {p.champion}
                      {p.isJungle && (
                        <span className="mc-jg" title="Jungle (has Smite)">
                          JG
                        </span>
                      )}
                    </span>
                    <span className="mc-id">{p.riotId}</span>
                  </div>
                  {p.rank && <span className="mc-rank">{p.rank}</span>}
                </div>
              ))}
            </div>
          );
        })}
      </div>

      {match.bans.length > 0 && (
        <div className="mc-bans">
          <span className="mc-bans-label">Bans</span>
          {match.bans.map((b, i) => (
            <Champ key={i} name={b} icons={icons} />
          ))}
        </div>
      )}
    </div>
  );
}
