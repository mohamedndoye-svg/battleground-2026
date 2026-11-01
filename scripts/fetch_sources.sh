#!/usr/bin/env bash
# Download every source page the build scripts read into cache/ (wiki/, gv/, w270/).
# Polite pacing: Wikipedia rate-limits bursts, so one request every ~3s with retries.
set -u
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
C="$ROOT/cache"
mkdir -p "$C/wiki" "$C/gv" "$C/w270"
UA='BattlegroundTracker/1.0 (personal non-commercial dashboard; https://claude.ai) curl/8'

get() {  # get <url> <outfile>
  local url="$1" out="$2" n=0
  for try in 1 2 3; do
    curl -s -m 60 -A "$UA" "$url" -o "$out"
    n=$(wc -c < "$out" 2>/dev/null || echo 0)
    [ "$n" -gt 5000 ] && break
    sleep $((try * 8))
  done
  printf '%s %9s %s\n' "$(date -u +%FT%TZ)" "$n" "$url"
  sleep 3
}

W=https://en.wikipedia.org/wiki
get "$W/2026_United_States_Senate_elections" "$C/wiki/2026_United_States_Senate_elections.html"
get "$W/2026_United_States_House_of_Representatives_election_ratings" "$C/wiki/house_ratings.html"
get "$W/2026_United_States_House_of_Representatives_elections" "$C/wiki/2026_United_States_House_of_Representatives_elections.html"
get "$W/2026_United_States_gubernatorial_elections" "$C/wiki/gov.html"
get "$W/2024_United_States_presidential_election" "$C/wiki/pres2024.html"
for s in Alaska Iowa Kansas Maine Michigan Minnesota Nebraska New_Hampshire North_Carolina South_Carolina Texas; do
  get "$W/2026_United_States_Senate_election_in_$s" "$C/wiki/sen_$s.html"
done
get "$W/2026_United_States_Senate_special_election_in_Ohio" "$C/wiki/2026_United_States_Senate_special_election_in_Ohio.html"
for s in Alaska Arizona Florida Georgia Iowa Kansas Michigan Nebraska Nevada Ohio Oregon Texas Vermont Wisconsin; do
  get "$W/2026_${s}_gubernatorial_election" "$C/wiki/gov_$s.html"
done
for t in 2026_United_States_Senate_election_in_Georgia 2026_Georgia_gubernatorial_election 2026_Georgia_lieutenant_gubernatorial_election \
         2026_Georgia_Secretary_of_State_election 2026_Georgia_Attorney_General_election 2026_Georgia_Agriculture_Commissioner_election \
         2026_Georgia_Insurance_Commissioner_election 2026_Georgia_Labor_Commissioner_election \
         2026_Georgia_State_Superintendent_of_Schools_election 2026_Georgia_Public_Service_Commission_election; do
  get "$W/$t" "$C/wiki/$t.html"
done
get "$W/Gwinnett_County,_Georgia" "$C/wiki/gwinnett.html"
get "https://www.270towin.com/2026-house-election/" "$C/w270/house.html"
for p in "" county ushouse; do get "https://georgiavotes.com/$p" "$C/gv/gv_${p:-home}.html"; done
get "https://georgiavotes.com/county?c=67" "$C/gv/gv_c67.html"
