#!/usr/bin/env python3
"""
Prompt Cache API — Zeug Lab
Deploys to Render (Flask + SQLite)
"""

import os
import json
import hashlib
import sqlite3
import time
from datetime import datetime

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS
import requests

app = Flask(__name__)
# Allow all origins for demo — restrict in production
CORS(app, resources={r"/api/*": {"origins": "*"}})

DB_PATH = os.path.join(os.path.dirname(__file__), "cache.db")
KIE_KEY = os.environ.get("KIE_AI_API_KEY", "")

# ── Seed data ───────────────────────────────────────────────────
SEED_PROMPTS = [
    {
        "prompt": "What are the 15 rules to reduce AI token consumption?",
        "response": "Nate B. Jones identifies 3 levels: (1) Manual habits—compress prompts, remove fluff, use structured output; (2) Middleware—prompt caching, semantic deduplication, response compression; (3) Architecture—model selection, streaming, batching. Key rules: clean your desk (remove context cruft), cache everything repeated, use cheaper models for pre-processing, stream responses, batch where possible.",
        "tokens_in": 420,
        "tokens_out": 1130,
        "hits": 9
    },
    {
        "prompt": "How does prompt caching reduce token costs?",
        "response": "Prompt caching stores repeated prompt prefixes and full prompts. On exact match: zero tokens sent to model. On semantic match: retrieve cached response without API call. Works best for SOPs, repeated queries, and agent loops. Can save 60-90% of token costs at scale.",
        "tokens_in": 280,
        "tokens_out": 720,
        "hits": 6
    },
    {
        "prompt": "What is the Ringer multi-agent framework?",
        "response": "Ringer is a local intermediary that sits between your application and AI models. It handles routing, caching, fallback, and load balancing across multiple providers. Designed for resilience: if one provider fails, Ringer routes to another without application changes.",
        "tokens_in": 310,
        "tokens_out": 870,
        "hits": 2
    },
    {
        "prompt": "Explain the 'clean your desk' metaphor for token optimization",
        "response": "The desk metaphor: Level 1 optimization is like cleaning your physical desk—remove everything not needed for the current task. In prompt terms: strip system messages, remove conversation history cruft, use concise instructions. A clean prompt = fewer tokens = lower cost + faster response.",
        "tokens_in": 250,
        "tokens_out": 720,
        "hits": 2
    },
    {
        "prompt": "How can SOPs be combined with prompt caching for asymmetric performance?",
        "response": "Insert Zeug SOPs as cached system prompts. Each agent call references the cached SOP by hash instead of sending full text. With semantic caching, even paraphrased requests hit the SOP cache. Result: complex 2000-token SOPs compress to a 64-byte hash reference. Asymmetric improvement: tiny prompt → huge cached context.",
        "tokens_in": 380,
        "tokens_out": 1020,
        "hits": 1
    },
    {
        "prompt": "What is ClawPanel's Prompt Caching API?",
        "response": "A workspace-level proxy that intercepts prompts before they reach any model provider. Features: exact-match cache, semantic similarity search via embeddings, per-workspace scoping, RLS isolation, hit-rate analytics. Drops into existing apps with a single URL change.",
        "tokens_in": 340,
        "tokens_out": 860,
        "hits": 1
    }
]

# ── DB ──────────────────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS cache_entries (
            id INTEGER PRIMARY KEY,
            prompt_hash TEXT UNIQUE,
            prompt_text TEXT,
            response_text TEXT,
            model TEXT,
            provider TEXT,
            tokens_in INTEGER,
            tokens_out INTEGER,
            created_at REAL,
            hit_count INTEGER DEFAULT 1,
            embedding BLOB
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY,
            prompt_hash TEXT,
            was_hit BOOLEAN,
            tokens_in INTEGER,
            tokens_out INTEGER,
            latency_ms REAL,
            created_at REAL
        )
    ''')
    conn.commit()
    conn.close()

def seed_db():
    """Populate demo data if empty."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM cache_entries")
    if c.fetchone()[0] > 0:
        conn.close()
        return
    
    for item in SEED_PROMPTS:
        h = hashlib.sha256(item["prompt"].encode()).hexdigest()[:32]
        c.execute('''INSERT INTO cache_entries 
            (prompt_hash, prompt_text, response_text, model, provider, tokens_in, tokens_out, created_at, hit_count)
            VALUES (?,?,?,?,?,?,?,?,?)''',
            (h, item["prompt"], item["response"], "claude-sonnet-4", "anthropic",
             item["tokens_in"], item["tokens_out"], time.time(), item["hits"]))
        # Record the initial hits as calls
        for _ in range(item["hits"]):
            c.execute('''INSERT INTO calls 
                (prompt_hash, was_hit, tokens_in, tokens_out, latency_ms, created_at)
                VALUES (?,1,?,?,0,?)''',
                (h, item["tokens_in"], item["tokens_out"], time.time()))
    conn.commit()
    conn.close()

def db_conn():
    return sqlite3.connect(DB_PATH)

init_db()
seed_db()

# ── Hash ─────────────────────────────────────────────────────────
def hash_prompt(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:32]

# ── Embedding (via KIE AI) ──────────────────────────────────────
def get_embedding(text: str) -> list:
    if not KIE_KEY:
        return []
    try:
        r = requests.post(
            "https://api.kie.ai/v1/embeddings",
            headers={"Authorization": f"Bearer {KIE_KEY}", "Content-Type": "application/json"},
            json={"input": text, "model": "text-embedding-3-small"},
            timeout=30
        )
        if r.status_code == 200:
            return r.json()["data"][0]["embedding"]
    except Exception:
        pass
    return []

def cosine_similarity(a: list, b: list) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x*y for x,y in zip(a,b))
    norm_a = sum(x*x for x in a) ** 0.5
    norm_b = sum(x*x for x in b) ** 0.5
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

# ── API Routes ───────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template_string(DASHBOARD_HTML)

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "version": "1.0.0", "cached_entries": _count_entries()})

@app.route("/api/cache/list")
def cache_list():
    """Return all cached entries for the atlas."""
    conn = db_conn()
    c = conn.cursor()
    c.execute('''SELECT prompt_text, response_text, hit_count, tokens_in, tokens_out, created_at 
                 FROM cache_entries ORDER BY hit_count DESC''')
    rows = []
    for r in c.fetchall():
        rows.append({
            "prompt": r[0],
            "response_preview": r[1][:200] + "..." if len(r[1]) > 200 else r[1],
            "hits": r[2],
            "tokens": r[3] + r[4],
            "created_at": datetime.fromtimestamp(r[5]).isoformat()
        })
    conn.close()
    return jsonify(rows)

@app.route("/api/cache/check", methods=["POST"])
def cache_check():
    data = request.json or {}
    prompt = data.get("prompt", "").strip()
    model = data.get("model", "claude-sonnet-4")
    provider = data.get("provider", "anthropic")
    threshold = data.get("threshold", 0.95)
    
    if not prompt:
        return jsonify({"error": "prompt required"}), 400
    
    h = hash_prompt(prompt)
    conn = db_conn()
    c = conn.cursor()
    
    # Exact match first
    c.execute("SELECT response_text, tokens_in, tokens_out, hit_count FROM cache_entries WHERE prompt_hash=?", (h,))
    row = c.fetchone()
    
    if row:
        c.execute("UPDATE cache_entries SET hit_count = hit_count + 1 WHERE prompt_hash=?", (h,))
        c.execute("INSERT INTO calls (prompt_hash, was_hit, tokens_in, tokens_out, latency_ms, created_at) VALUES (?,1,?,?,0,?)",
                  (h, row[1], row[2], time.time()))
        conn.commit()
        conn.close()
        return jsonify({
            "cached": True,
            "match_type": "exact",
            "response": row[0],
            "tokens_saved": row[1] + row[2],
            "original_cost": f"${(row[1]+row[2])*0.000003:.4f}",
            "hit_count": row[3] + 1
        })
    
    # Semantic match (if embedding available)
    emb = get_embedding(prompt)
    if emb:
        c.execute("SELECT prompt_hash, prompt_text, response_text, tokens_in, tokens_out, embedding, hit_count FROM cache_entries WHERE embedding IS NOT NULL")
        best_sim = 0
        best_row = None
        for r in c.fetchall():
            try:
                stored = json.loads(r[5])
                sim = cosine_similarity(emb, stored)
                if sim > best_sim and sim >= threshold:
                    best_sim = sim
                    best_row = r
            except:
                continue
        
        if best_row:
            c.execute("UPDATE cache_entries SET hit_count = hit_count + 1 WHERE prompt_hash=?", (best_row[0],))
            c.execute("INSERT INTO calls (prompt_hash, was_hit, tokens_in, tokens_out, latency_ms, created_at) VALUES (?,1,?,?,0,?)",
                      (best_row[0], best_row[3], best_row[4], time.time()))
            conn.commit()
            conn.close()
            return jsonify({
                "cached": True,
                "match_type": "semantic",
                "similarity": round(best_sim, 4),
                "response": best_row[2],
                "tokens_saved": best_row[3] + best_row[4],
                "hit_count": best_row[6] + 1
            })
    
    conn.close()
    return jsonify({"cached": False, "prompt_hash": h})

@app.route("/api/cache/store", methods=["POST"])
def cache_store():
    data = request.json or {}
    prompt = data.get("prompt", "").strip()
    response = data.get("response", "").strip()
    model = data.get("model", "claude-sonnet-4")
    provider = data.get("provider", "anthropic")
    tokens_in = data.get("tokens_in", 0)
    tokens_out = data.get("tokens_out", 0)
    
    if not prompt or not response:
        return jsonify({"error": "prompt and response required"}), 400
    
    h = hash_prompt(prompt)
    emb = get_embedding(prompt)
    emb_blob = json.dumps(emb) if emb else None
    
    conn = db_conn()
    c = conn.cursor()
    c.execute('''INSERT OR REPLACE INTO cache_entries 
        (prompt_hash, prompt_text, response_text, model, provider, tokens_in, tokens_out, created_at, embedding)
        VALUES (?,?,?,?,?,?,?,?,?)''',
        (h, prompt, response, model, provider, tokens_in, tokens_out, time.time(), emb_blob))
    c.execute("INSERT INTO calls (prompt_hash, was_hit, tokens_in, tokens_out, latency_ms, created_at) VALUES (?,0,?,?,0,?)",
              (h, tokens_in, tokens_out, time.time()))
    conn.commit()
    conn.close()
    
    return jsonify({"stored": True, "prompt_hash": h})

@app.route("/api/stats")
def stats():
    conn = db_conn()
    c = conn.cursor()
    
    c.execute("SELECT COUNT(*) FROM cache_entries")
    total_cached = c.fetchone()[0]
    
    c.execute("SELECT COUNT(*), SUM(tokens_in), SUM(tokens_out) FROM calls WHERE was_hit=1")
    hits = c.fetchone()
    total_hits = hits[0] or 0
    tokens_saved = (hits[1] or 0) + (hits[2] or 0)
    
    c.execute("SELECT COUNT(*), SUM(tokens_in), SUM(tokens_out) FROM calls WHERE was_hit=0")
    misses = c.fetchone()
    total_misses = misses[0] or 0
    
    c.execute("SELECT prompt_text, response_text, hit_count, tokens_in+tokens_out as ttl FROM cache_entries ORDER BY hit_count DESC LIMIT 10")
    top = [{"prompt": r[0][:100]+"...", "response": r[1][:100]+"...", "hits": r[2], "tokens": r[3]} for r in c.fetchall()]
    
    conn.close()
    
    total = total_hits + total_misses
    hit_rate = (total_hits / total * 100) if total > 0 else 0
    
    return jsonify({
        "total_cached": total_cached,
        "total_calls": total,
        "hits": total_hits,
        "misses": total_misses,
        "hit_rate_percent": round(hit_rate, 2),
        "tokens_saved": tokens_saved,
        "estimated_cost_saved_usd": round(tokens_saved * 0.000003, 4),
        "top_cached": top
    })

@app.route("/api/calls")
def calls():
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT prompt_hash, was_hit, tokens_in, tokens_out, created_at FROM calls ORDER BY created_at DESC LIMIT 50")
    rows = [{"hash": r[0][:16], "hit": bool(r[1]), "tokens": r[2]+r[3], "time": datetime.fromtimestamp(r[4]).isoformat()} for r in c.fetchall()]
    conn.close()
    return jsonify(rows)

def _count_entries():
    conn = db_conn()
    c = conn.cursor()
    c.execute("SELECT COUNT(*) FROM cache_entries")
    n = c.fetchone()[0]
    conn.close()
    return n

# ── Built-in Admin Dashboard ─────────────────────────────────────
DASHBOARD_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Zeug Prompt Cache — Admin</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
:root{--ink:#0b0b0d;--bone:#f1f0ec;--fog:#55555c;--accent:#ff6b35;--accent2:#4ecdc4;}
*{box-sizing:border-box;margin:0;padding:0;font-family:'IBM Plex Mono',monospace;}
body{background:var(--ink);color:var(--bone);min-height:100vh;}
header{padding:2rem;border-bottom:1px solid #222;}
h1{font-size:1.5rem;letter-spacing:-0.02em;} h1 span{color:var(--accent);}
.sub{color:var(--fog);font-size:0.8rem;margin-top:0.5rem;}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:1rem;padding:2rem;}
.card{background:#151518;border:1px solid #222;border-radius:8px;padding:1.5rem;}
.card h3{font-size:0.7rem;text-transform:uppercase;color:var(--fog);margin-bottom:0.5rem;letter-spacing:0.05em;}
.card .big{font-size:2rem;font-weight:700;color:var(--accent);}
.card .unit{font-size:0.7rem;color:var(--fog);}
#graph{height:400px;background:#0d0d10;border:1px solid #222;border-radius:8px;margin:0 2rem 2rem;}
table{width:100%;border-collapse:collapse;font-size:0.75rem;}
th,td{padding:0.5rem;text-align:left;border-bottom:1px solid #222;}
th{color:var(--fog);text-transform:uppercase;font-size:0.65rem;letter-spacing:0.05em;}
tr:hover{background:#1a1a1e;}
.section{padding:0 2rem 2rem;}
#test-area{background:#151518;border:1px solid #222;border-radius:8px;padding:1.5rem;margin:0 2rem 2rem;}
textarea{width:100%;background:#0d0d10;border:1px solid #333;color:var(--bone);padding:0.75rem;font-family:inherit;font-size:0.8rem;border-radius:4px;resize:vertical;}
button{background:var(--accent);color:var(--ink);border:none;padding:0.6rem 1.2rem;font-family:inherit;font-size:0.75rem;font-weight:700;cursor:pointer;border-radius:4px;margin-top:0.5rem;}
button:hover{opacity:0.9;} #result{margin-top:1rem;padding:1rem;background:#0d0d10;border-radius:4px;font-size:0.75rem;min-height:3rem;}
.hit{color:var(--accent2);}.miss{color:var(--accent);}
@media(max-width:768px){.grid{grid-template-columns:1fr;}#graph{margin:0 1rem 1rem;height:300px;}#test-area{margin:0 1rem 1rem;}.section{padding:0 1rem 1rem;}header{padding:1.5rem 1rem;}}
</style>
</head>
<body>
<header><h1>Zeug <span>Prompt Cache</span> Atlas — Admin</h1><div class="sub">Real-time token savings · Semantic caching · Knowledge graph</div></header>
<div class="grid" id="stats">
<div class="card"><h3>Cache Entries</h3><div class="big" id="s-cached">0</div></div>
<div class="card"><h3>Hit Rate</h3><div class="big" id="s-rate">0%</div></div>
<div class="card"><h3>Tokens Saved</h3><div class="big" id="s-saved">0</div><div class="unit" id="s-usd">$0.00</div></div>
<div class="card"><h3>Total Calls</h3><div class="big" id="s-calls">0</div></div>
</div>
<div id="test-area">
<h3 style="font-size:0.75rem;text-transform:uppercase;color:var(--fog);margin-bottom:0.75rem;">Test Cache</h3>
<textarea id="prompt" rows="3" placeholder="Enter a prompt to test caching..."></textarea><br>
<button onclick="testCache()">Check Cache</button>
<button onclick="storeCache()" style="background:var(--fog);color:var(--bone);margin-left:0.5rem;">Store Response</button>
<div id="result"></div>
</div>
<div id="graph"></div>
<div class="section">
<h3 style="font-size:0.75rem;text-transform:uppercase;color:var(--fog);margin-bottom:0.75rem;">Recent Calls</h3>
<table id="calls-table"><thead><tr><th>Time</th><th>Type</th><th>Hash</th><th>Tokens</th></tr></thead><tbody></tbody></table>
</div>
<script>
async function loadStats(){
  const r=await fetch('/api/stats'); const d=await r.json();
  document.getElementById('s-cached').textContent=d.total_cached;
  document.getElementById('s-rate').textContent=d.hit_rate_percent+'%';
  document.getElementById('s-saved').textContent=d.tokens_saved.toLocaleString();
  document.getElementById('s-usd').textContent='$'+d.estimated_cost_saved_usd;
  document.getElementById('s-calls').textContent=d.total_calls;
  const nodes=d.top_cached.map((t,i)=>({id:i,name:t.prompt.slice(0,30),tokens:t.tokens,hits:t.hits}));
  const links=[];
  for(let i=0;i<nodes.length;i++)for(let j=i+1;j<nodes.length;j++)links.push({source:i,target:j,value:Math.max(1,5-Math.abs(nodes[i].hits-nodes[j].hits))});
  drawGraph(nodes,links);
}
function drawGraph(nodes,links){
  const w=document.getElementById('graph').clientWidth,h=400;
  d3.select('#graph').selectAll('*').remove();
  const svg=d3.select('#graph').append('svg').attr('width',w).attr('height',h);
  const sim=d3.forceSimulation(nodes).force('link',d3.forceLink(links).id(d=>d.id).distance(80)).force('charge',d3.forceManyBody().strength(-200)).force('center',d3.forceCenter(w/2,h/2));
  svg.append('g').selectAll('line').data(links).join('line').attr('stroke','#333').attr('stroke-width',1);
  const node=svg.append('g').selectAll('circle').data(nodes).join('circle').attr('r',d=>8+d.hits*2).attr('fill','#ff6b35').attr('opacity',0.8).call(d3.drag().on('start',(e,d)=>{if(!e.active)sim.alphaTarget(0.3).restart();d.fx=d.x;d.fy=d.y;}).on('drag',(e,d)=>{d.fx=e.x;d.fy=e.y;}).on('end',(e,d)=>{if(!e.active)sim.alphaTarget(0);d.fx=null;d.fy=null;}));
  svg.append('g').selectAll('text').data(nodes).join('text').text(d=>d.name).attr('x',d=>d.x).attr('y',d=>d.y-12).attr('fill','#888').attr('font-size','10px').attr('text-anchor','middle');
  sim.on('tick',()=>{svg.selectAll('line').attr('x1',d=>d.source.x).attr('y1',d=>d.source.y).attr('x2',d=>d.target.x).attr('y2',d=>d.target.y);node.attr('cx',d=>d.x).attr('cy',d=>d.y);svg.selectAll('text').attr('x',d=>d.x).attr('y',d=>d.y-12);});
}
async function testCache(){
  const p=document.getElementById('prompt').value; if(!p)return;
  const r=await fetch('/api/cache/check',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:p})});
  const d=await r.json(); const el=document.getElementById('result');
  if(d.cached)el.innerHTML='<span class="hit">CACHE HIT \u2713</span> ('+d.match_type+') Saved '+d.tokens_saved+' tokens. Hits: '+d.hit_count;
  else el.innerHTML='<span class="miss">CACHE MISS</span> Hash: '+d.prompt_hash;
  loadStats();
}
async function storeCache(){
  const p=document.getElementById('prompt').value; if(!p)return;
  const r=await fetch('/api/cache/store',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({prompt:p,response:'Sample cached response for: '+p.slice(0,50),tokens_in:p.length*2,tokens_out:150})});
  const d=await r.json(); document.getElementById('result').innerHTML='<span class="hit">STORED \u2713</span> Hash: '+d.prompt_hash;
  loadStats();
}
async function loadCalls(){
  const r=await fetch('/api/calls'); const d=await r.json();
  const tbody=document.querySelector('#calls-table tbody');
  tbody.innerHTML=d.map(c=>'<tr><td>'+c.time+'</td><td class="'+(c.hit?'hit':'miss')+'">'+(c.hit?'HIT':'MISS')+'</td><td>'+c.hash+'</td><td>'+c.tokens+'</td></tr>').join('');
}
loadStats();loadCalls(); setInterval(()=>{loadStats();loadCalls();},5000);
</script>
</body>
</html>"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8787)), debug=False)
