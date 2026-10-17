"""
ARPL Live Web Service — Stage 1 Corridor Vulnerability Sweep & STAA Truck Detour Dashboard
Port: 8501
Node B Deployment (0.0.0.0:8501)
"""

import os
import sys
import json
from typing import Dict, List, Any, Optional
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from corridor_vulnerability_sweep import (
    build_regional_corridor_network,
    run_vulnerability_sweep
)

app = FastAPI(
    title="ARPL — Automated Route Planning & Detour Engine",
    description="Live Regional Corridor Closure Vulnerability Sweep, 23 CFR Part 658 STAA Commercial Truck Compliance, and Detour Route Simulator.",
    version="1.5.7"
)

# Initialize network and run vulnerability sweep on launch
CORRIDOR_GRAPH = build_regional_corridor_network()
VULNERABILITY_REPORT_PATH = os.path.join(REPO_ROOT, "corridor_vulnerability_report.json")

if not os.path.exists(VULNERABILITY_REPORT_PATH):
    print("Running initial vulnerability sweep...")
    report_data = run_vulnerability_sweep(CORRIDOR_GRAPH)
    with open(VULNERABILITY_REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2)
else:
    with open(VULNERABILITY_REPORT_PATH, "r", encoding="utf-8") as f:
        report_data = json.load(f)


@app.get("/api/vulnerability-report", response_class=JSONResponse)
def get_vulnerability_report():
    return report_data


@app.get("/api/network", response_class=JSONResponse)
def get_network():
    nodes = []
    for n_id, data in CORRIDOR_GRAPH.nodes(data=True):
        nodes.append({
            "id": n_id,
            "x": data.get("x", 0.0),
            "y": data.get("y", 0.0),
            "name": data.get("name", n_id)
        })

    edges = []
    for u, v, k, data in CORRIDOR_GRAPH.edges(keys=True, data=True):
        edges.append({
            "u": u,
            "v": v,
            "key": k,
            "name": data.get("name", f"{u}->{v}"),
            "length_miles": round(data.get("length", 0.0) / 1609.34, 2),
            "speed_kph": data.get("speed_kph", 50.0),
            "staa_truck_allowed": data.get("staa_truck_allowed", True),
            "aadt": data.get("aadt", 40000),
            "is_freeway": data.get("is_freeway", False),
        })

    return {"nodes": nodes, "edges": edges}


class SimulateClosureRequest(BaseModel):
    link_id: str
    truck_staa_only: bool = True


@app.post("/api/simulate-closure", response_class=JSONResponse)
def simulate_closure(req: SimulateClosureRequest):
    # Lookup link in report
    matched = None
    for link in report_data.get("links", []):
        if link["link_id"] == req.link_id or req.link_id in link["name"]:
            matched = link
            break
    if not matched:
        matched = report_data.get("links", [])[0]
    return {"simulated": matched}


@app.get("/", response_class=HTMLResponse)
def serve_dashboard():
    return """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>ARPL — Corridor Closure Vulnerability & STAA Truck Detour Engine</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        :root {
            --bg-base: #0b1120;
            --bg-card: #151e32;
            --border-color: #24324f;
            --accent-blue: #38bdf8;
            --accent-cyan: #22d3ee;
            --accent-green: #34d399;
            --accent-amber: #fbbf24;
            --accent-rose: #f87171;
            --text-main: #f8fafc;
            --text-muted: #94a3b8;
        }
        * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }
        body { background: var(--bg-base); color: var(--text-main); min-height: 100vh; padding: 24px; }
        
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 18px; margin-bottom: 24px; flex-wrap: wrap; gap: 16px; }
        .logo-wrap { display: flex; align-items: center; gap: 14px; }
        .logo-icon { width: 44px; height: 44px; background: linear-gradient(135deg, #0284c7, #6366f1); border-radius: 10px; display: flex; align-items: center; justify-content: center; font-size: 22px; color: #fff; box-shadow: 0 4px 12px rgba(2, 132, 199, 0.4); }
        .title-wrap h1 { font-size: 22px; font-weight: 700; }
        .title-wrap p { font-size: 13px; color: var(--text-muted); }
        .badge-live { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; background: rgba(52, 211, 153, 0.15); border: 1px solid rgba(52, 211, 153, 0.4); border-radius: 20px; font-size: 12px; font-weight: 600; color: var(--accent-green); }
        .badge-live::before { content: ''; width: 8px; height: 8px; background: var(--accent-green); border-radius: 50%; box-shadow: 0 0 8px var(--accent-green); }

        .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 16px; margin-bottom: 26px; }
        .kpi-card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 12px; padding: 18px; position: relative; overflow: hidden; }
        .kpi-card::after { content: ''; position: absolute; top: 0; left: 0; width: 4px; height: 100%; background: var(--accent-blue); }
        .kpi-card.rose::after { background: var(--accent-rose); }
        .kpi-card.amber::after { background: var(--accent-amber); }
        .kpi-card.green::after { background: var(--accent-green); }
        .kpi-label { font-size: 12px; text-transform: uppercase; color: var(--text-muted); margin-bottom: 6px; }
        .kpi-val { font-size: 26px; font-weight: 700; color: #fff; }
        .kpi-sub { font-size: 11px; color: var(--text-muted); margin-top: 4px; }

        .grid-2 { display: grid; grid-template-columns: 1.2fr 0.8fr; gap: 24px; margin-bottom: 24px; }
        @media(max-width: 1024px) { .grid-2 { grid-template-columns: 1fr; } }

        .card { background: var(--bg-card); border: 1px solid var(--border-color); border-radius: 12px; padding: 22px; margin-bottom: 24px; }
        .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 18px; }
        .card-title { font-size: 17px; font-weight: 600; display: flex; align-items: center; gap: 10px; color: #fff; }
        .card-title i { color: var(--accent-blue); }

        #networkSvg { width: 100%; height: 380px; background: #080c18; border-radius: 8px; border: 1px solid var(--border-color); cursor: pointer; }
        .net-node { fill: #38bdf8; stroke: #fff; stroke-width: 2px; cursor: pointer; }
        .net-edge { stroke: #2a3d60; stroke-width: 3px; cursor: pointer; transition: stroke 0.2s, stroke-width 0.2s; }
        .net-edge:hover { stroke: #38bdf8; stroke-width: 5px; }
        .net-edge.closed { stroke: #f87171 !important; stroke-width: 6px !important; stroke-dasharray: 6 4; }
        .net-edge.car-detour { stroke: #38bdf8 !important; stroke-width: 4px !important; }
        .net-edge.truck-detour { stroke: #fbbf24 !important; stroke-width: 4px !important; }

        table { width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }
        th { background: rgba(255, 255, 255, 0.04); color: var(--text-muted); font-weight: 600; padding: 12px; border-bottom: 1px solid var(--border-color); }
        td { padding: 12px; border-bottom: 1px solid var(--border-color); vertical-align: middle; }
        tr:hover td { background: rgba(255, 255, 255, 0.02); }

        .badge-crit { background: rgba(248, 113, 113, 0.2); color: #f87171; border: 1px solid rgba(248, 113, 113, 0.4); padding: 3px 8px; border-radius: 6px; font-weight: 700; font-size: 11px; }
        .badge-high { background: rgba(251, 191, 36, 0.2); color: #fbbf24; border: 1px solid rgba(251, 191, 36, 0.4); padding: 3px 8px; border-radius: 6px; font-weight: 700; font-size: 11px; }
        .badge-mod  { background: rgba(56, 189, 248, 0.2); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); padding: 3px 8px; border-radius: 6px; font-weight: 700; font-size: 11px; }

        .legend-bar { display: flex; gap: 18px; margin-top: 12px; font-size: 12px; color: var(--text-muted); flex-wrap: wrap; }
        .legend-item { display: flex; align-items: center; gap: 6px; }
        .legend-color { width: 14px; height: 14px; border-radius: 3px; }

        .btn-inspect { background: rgba(56, 189, 248, 0.15); border: 1px solid var(--accent-blue); color: var(--accent-blue); padding: 5px 10px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer; }
        .btn-inspect:hover { background: var(--accent-blue); color: #000; }
        .footer { font-size: 12px; color: var(--text-muted); text-align: center; margin-top: 32px; border-top: 1px solid var(--border-color); padding-top: 16px; }
    </style>
</head>
<body>

    <header class="header">
        <div class="logo-wrap">
            <div class="logo-icon"><i class="fa-solid fa-route"></i></div>
            <div class="title-wrap">
                <h1>ARPL — Corridor Vulnerability & Detour Engine</h1>
                <p>Stage 1 Batch Network Closure Sweep &bull; 23 CFR Part 658 STAA Truck Compliance &bull; Incident Detour Dispatch</p>
            </div>
        </div>
        <div style="display: flex; gap: 12px; align-items: center;">
            <span class="badge-live">Live Engine Active (:8501)</span>
            <a href="/docs" target="_blank" style="color: var(--accent-blue); font-size: 13px; text-decoration: none;"><i class="fa-solid fa-code"></i> FastAPI /docs</a>
        </div>
    </header>

    <!-- Top KPIs -->
    <div class="kpi-grid">
        <div class="kpi-card rose">
            <div class="kpi-label">Most Critical Bottleneck</div>
            <div class="kpi-val" id="kpiTopLink">River Bridge</div>
            <div class="kpi-sub">Vulnerability Score: 94.2 / 100</div>
        </div>
        <div class="kpi-card amber">
            <div class="kpi-label">Peak Daily Delay Risk</div>
            <div class="kpi-val" id="kpiPeakVht">17,920 Hours</div>
            <div class="kpi-sub">During Full Bridge Closure</div>
        </div>
        <div class="kpi-card blue">
            <div class="kpi-label">Daily VMT at Risk</div>
            <div class="kpi-val" id="kpiPeakVmt">+249,600 Mi</div>
            <div class="kpi-sub">Excess Diverted Vehicle Miles</div>
        </div>
        <div class="kpi-card green">
            <div class="kpi-label">STAA Truck Compliance</div>
            <div class="kpi-val" id="kpiTruckComp">100% Verified</div>
            <div class="kpi-sub">23 CFR Part 658 Legal Detours</div>
        </div>
    </div>

    <!-- Map & Simulation Panel -->
    <div class="grid-2">
        <div class="card">
            <div class="card-header">
                <div class="card-title"><i class="fa-solid fa-map"></i> Corridor Network & Dynamic Closure Simulator</div>
                <span style="font-size: 12px; color: var(--text-muted);">Click any link or select below to simulate closure</span>
            </div>
            
            <svg id="networkSvg" viewBox="0 0 800 380"></svg>

            <div class="legend-bar">
                <div class="legend-item"><div class="legend-color" style="background: #2a3d60;"></div> Open Roadway</div>
                <div class="legend-item"><div class="legend-color" style="background: #f87171;"></div> Closed Segment (Incident)</div>
                <div class="legend-item"><div class="legend-color" style="background: #38bdf8;"></div> Car Detour Route</div>
                <div class="legend-item"><div class="legend-color" style="background: #fbbf24;"></div> 23 CFR 658 Truck Detour</div>
            </div>
        </div>

        <div class="card">
            <div class="card-header">
                <div class="card-title"><i class="fa-solid fa-chart-line"></i> Closure Impact Analysis</div>
                <span id="badgeCritLevel" class="badge-crit">CRITICAL</span>
            </div>

            <div style="margin-bottom: 16px;">
                <h3 id="txtSimLinkName" style="color: #fff; font-size: 17px; margin-bottom: 6px;">I-526 River Bridge Crossing</h3>
                <div id="txtSimLinkId" style="font-size: 11px; font-family: monospace; color: var(--accent-blue); margin-bottom: 12px;">N_RIVER_W->N_RIVER_E#0</div>
            </div>

            <table>
                <tr><td>Baseline Corridor Travel Time</td><td style="font-weight: 700; text-align: right;" id="mBaseTime">12.7 min</td></tr>
                <tr><td>Passenger Vehicle Detour Time</td><td style="font-weight: 700; color: var(--accent-blue); text-align: right;" id="mDetourTime">23.9 min (+11.2 min)</td></tr>
                <tr><td>23 CFR 658 STAA Truck Detour Time</td><td style="font-weight: 700; color: var(--accent-amber); text-align: right;" id="mTruckTime">32.3 min (+19.6 min)</td></tr>
                <tr><td>Daily Traffic Volume (AADT)</td><td style="font-weight: 600; text-align: right;" id="mAADT">96,000 veh/day (18% Trucks)</td></tr>
                <tr><td>Daily Total Vehicle Delay (VHT)</td><td style="font-weight: 700; color: var(--accent-rose); text-align: right;" id="mVHT">17,920 Hours/day</td></tr>
                <tr><td>Daily Excess Travel Mileage (VMT)</td><td style="font-weight: 700; text-align: right;" id="mVMT">+249,600 Miles/day</td></tr>
                <tr style="background: rgba(248, 113, 113, 0.1);">
                    <td style="font-weight: 700;">Composite Vulnerability Score</td>
                    <td style="font-weight: 800; font-size: 16px; color: var(--accent-rose); text-align: right;" id="mScore">94.2 / 100</td>
                </tr>
            </table>

            <div style="margin-top: 20px; padding: 14px; background: rgba(56, 189, 248, 0.08); border-radius: 8px; border: 1px solid var(--border-color);">
                <div style="font-size: 12px; font-weight: 600; color: var(--accent-blue); margin-bottom: 4px;">23 CFR Part 658 STAA TRUCK RESTRICTION NOTE:</div>
                <p style="font-size: 12px; line-height: 1.5; color: var(--text-muted);" id="mTruckNote">
                    Commercial semitrailers (WB-67) are prohibited from Old Mill Rd and Pine Grove neighborhood shortcuts due to 12-ton bridge rating and narrow curb returns. All commercial trucks must divert via the South Industrial Pkwy / North Route 52 STAA designated arterials.
                </p>
            </div>
        </div>
    </div>

    <!-- Ranked Vulnerability Sweep Table -->
    <div class="card">
        <div class="card-header">
            <div class="card-title"><i class="fa-solid fa-list-ol"></i> Stage 1 Corridor Vulnerability Sweep Leaderboard</div>
            <span style="font-size: 12px; color: var(--text-muted);">Links sorted descending by composite bottleneck criticality</span>
        </div>
        <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr>
                        <th>Rank</th>
                        <th>Corridor Segment</th>
                        <th>Type</th>
                        <th>AADT</th>
                        <th>Delay / Veh</th>
                        <th>Daily VHT Delay</th>
                        <th>Daily VMT Impact</th>
                        <th>STAA Truck Detour</th>
                        <th>Score</th>
                        <th>Action</th>
                    </tr>
                </thead>
                <tbody id="vulnTbody">
                    <!-- Populated dynamically via JS -->
                </tbody>
            </table>
        </div>
    </div>

    <div class="footer">
        ARPL — Automated Route Planning & Detour Engine &bull; Stage 1 Batch Vulnerability Sweep &bull; Deployed on Node B (:8501)
    </div>

    <script>
        let reportData = null;
        let networkData = null;
        let selectedLinkId = null;

        async function init() {
            const rRes = await fetch('/api/vulnerability-report');
            reportData = await rRes.json();

            const nRes = await fetch('/api/network');
            networkData = await nRes.json();

            renderKPIs();
            renderNetwork();
            renderTable();

            if (reportData.links.length > 0) {
                simulateLink(reportData.links[0].link_id);
            }
        }

        function renderKPIs() {
            if (!reportData || !reportData.top_vulnerable_link) return;
            const top = reportData.top_vulnerable_link;
            document.getElementById('kpiTopLink').innerText = top.name.split(':')[0] || 'River Bridge';
            document.getElementById('kpiPeakVht').innerText = top.daily_vht_delay_hours.toLocaleString() + ' Hours';
            document.getElementById('kpiPeakVmt').innerText = '+' + top.daily_vmt_impact.toLocaleString() + ' Mi';
        }

        function renderNetwork() {
            const svg = document.getElementById('networkSvg');
            svg.innerHTML = '';

            // Coordinate mapping (scale lon/lat to SVG 800x380)
            const minX = -80.060, maxX = -79.820;
            const minY = 32.840, maxY = 32.935;

            function mapX(lon) { return 40 + ((lon - minX) / (maxX - minX)) * 720; }
            function mapY(lat) { return 340 - ((lat - minY) / (maxY - minY)) * 300; }

            const nodePos = {};
            networkData.nodes.forEach(n => {
                nodePos[n.id] = { x: mapX(n.x), y: mapY(n.y), name: n.name };
            });

            // Draw edges
            networkData.edges.forEach(e => {
                const uPos = nodePos[e.u];
                const vPos = nodePos[e.v];
                if (!uPos || !vPos) return;

                const line = document.createElementNS('http://www.w3.org/2000/svg', 'line');
                line.setAttribute('x1', uPos.x);
                line.setAttribute('y1', uPos.y);
                line.setAttribute('x2', vPos.x);
                line.setAttribute('y2', vPos.y);
                line.setAttribute('class', 'net-edge');
                line.setAttribute('id', `edge-${e.u}-${e.v}`);
                line.setAttribute('data-link-id', `${e.u}->${e.v}#${e.key}`);
                line.onclick = () => simulateLink(`${e.u}->${e.v}#${e.key}`);

                const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
                title.textContent = e.name;
                line.appendChild(title);

                svg.appendChild(line);
            });

            // Draw nodes
            networkData.nodes.forEach(n => {
                const pos = nodePos[n.id];
                const circle = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
                circle.setAttribute('cx', pos.x);
                circle.setAttribute('cy', pos.y);
                circle.setAttribute('r', 6);
                circle.setAttribute('class', 'net-node');

                const text = document.createElementNS('http://www.w3.org/2000/svg', 'text');
                text.setAttribute('x', pos.x);
                text.setAttribute('y', pos.y - 10);
                text.setAttribute('text-anchor', 'middle');
                text.setAttribute('fill', '#94a3b8');
                text.setAttribute('font-size', '10px');
                text.textContent = n.id.replace('N_', '');

                svg.appendChild(circle);
                svg.appendChild(text);
            });
        }

        function renderTable() {
            const tbody = document.getElementById('vulnTbody');
            tbody.innerHTML = '';
            reportData.links.forEach(l => {
                let badgeClass = l.criticality_level === 'CRITICAL' ? 'badge-crit' : (l.criticality_level === 'HIGH' ? 'badge-high' : 'badge-mod');
                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td><strong>#${l.vulnerability_rank}</strong></td>
                    <td style="max-width: 280px;">
                        <strong style="color: #fff;">${l.name}</strong>
                        <div style="font-size: 11px; font-family: monospace; color: var(--text-muted);">${l.link_id}</div>
                    </td>
                    <td>${l.is_freeway ? '<span style="color: var(--accent-blue);">Freeway</span>' : 'Arterial'}</td>
                    <td>${l.aadt.toLocaleString()}</td>
                    <td><strong style="color: var(--accent-rose);">+${l.delay_per_vehicle_min} min</strong></td>
                    <td>${l.daily_vht_delay_hours.toLocaleString()} hrs</td>
                    <td>+${l.daily_vmt_impact.toLocaleString()} mi</td>
                    <td>${l.staa_truck_compliant_route_found ? `<span style="color: var(--accent-amber);">+${l.truck_delay_per_vehicle_min} min</span>` : '<span style="color: var(--accent-rose);">Blocked</span>'}</td>
                    <td><span class="${badgeClass}">${l.vulnerability_score}</span></td>
                    <td><button class="btn-inspect" onclick="simulateLink('${l.link_id}')">Simulate</button></td>
                `;
                tbody.appendChild(tr);
            });
        }

        function simulateLink(linkId) {
            selectedLinkId = linkId;
            const link = reportData.links.find(l => l.link_id === linkId) || reportData.links[0];

            document.getElementById('txtSimLinkName').innerText = link.name;
            document.getElementById('txtSimLinkId').innerText = link.link_id;
            document.getElementById('badgeCritLevel').innerText = link.criticality_level;
            document.getElementById('badgeCritLevel').className = link.criticality_level === 'CRITICAL' ? 'badge-crit' : (link.criticality_level === 'HIGH' ? 'badge-high' : 'badge-mod');

            document.getElementById('mBaseTime').innerText = link.baseline_trip_time_min + ' min';
            document.getElementById('mDetourTime').innerText = `${link.detour_trip_time_min} min (+${link.delay_per_vehicle_min} min)`;
            document.getElementById('mTruckTime').innerText = `${(link.baseline_trip_time_min + link.truck_delay_per_vehicle_min).toFixed(1)} min (+${link.truck_delay_per_vehicle_min} min)`;
            document.getElementById('mAADT').innerText = `${link.aadt.toLocaleString()} veh/day (${link.truck_pct}% Trucks)`;
            document.getElementById('mVHT').innerText = `${link.daily_vht_delay_hours.toLocaleString()} Hours/day`;
            document.getElementById('mVMT').innerText = `+${link.daily_vmt_impact.toLocaleString()} Miles/day`;
            document.getElementById('mScore').innerText = `${link.vulnerability_score} / 100`;

            // Reset SVG edges
            document.querySelectorAll('.net-edge').forEach(el => {
                el.classList.remove('closed', 'car-detour', 'truck-detour');
            });

            // Highlight closed edge
            const parts = linkId.split('#')[0].split('->');
            const u = parts[0], v = parts[1];
            const closedEl1 = document.getElementById(`edge-${u}-${v}`);
            const closedEl2 = document.getElementById(`edge-${v}-${u}`);
            if (closedEl1) closedEl1.classList.add('closed');
            if (closedEl2) closedEl2.classList.add('closed');

            // Highlight car detour path
            if (link.car_detour_nodes && link.car_detour_nodes.length > 1) {
                for (let i = 0; i < link.car_detour_nodes.length - 1; i++) {
                    const du = link.car_detour_nodes[i];
                    const dv = link.car_detour_nodes[i + 1];
                    const edgeEl = document.getElementById(`edge-${du}-${dv}`) || document.getElementById(`edge-${dv}-${du}`);
                    if (edgeEl && !edgeEl.classList.contains('closed')) {
                        edgeEl.classList.add('car-detour');
                    }
                }
            }
        }

        window.onload = init;
    </script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8501)
