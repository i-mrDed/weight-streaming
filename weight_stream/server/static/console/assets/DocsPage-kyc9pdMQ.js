import{l as b,u as f,A as C,aU as O,t,a as L,d as n,Y as H,p as k}from"./index-CcYd6AHj.js";import{r as I,H as l,p as E,j as S,b as j,a as $}from"./markdown-BKWLVSNd.js";import{C as q}from"./Card-ClS9EoYs.js";import{T as A}from"./Tip-oiXbU2BI.js";import{E as N}from"./external-link-Bh4sSM8o.js";/* empty css              */const P=`\`\`\`bash\r
curl http://127.0.0.1:8765/v1/messages \\\r
  -H "Content-Type: application/json" \\\r
  -d '{\r
    "model": "default",\r
    "max_tokens": 256,\r
    "messages": [{"role": "user", "content": "Hello!"}]\r
  }'\r
\`\`\`\r
`,M=`\`\`\`javascript\r
const res = await fetch("http://127.0.0.1:8765/v1/messages", {\r
  method: "POST",\r
  headers: { "Content-Type": "application/json" },\r
  body: JSON.stringify({\r
    model: "default",\r
    max_tokens: 256,\r
    messages: [{ role: "user", content: "Hello!" }],\r
  }),\r
});\r
console.log(await res.json());\r
\`\`\`\r
`,U=`\`\`\`python\r
import requests\r
\r
r = requests.post(\r
    "http://127.0.0.1:8765/v1/messages",\r
    json={\r
        "model": "default",\r
        "max_tokens": 256,\r
        "messages": [{"role": "user", "content": "Hello!"}],\r
    },\r
    timeout=120,\r
)\r
print(r.json())\r
\`\`\`\r
`,D=`\`\`\`bash\r
# Cursor / Continue / Claude Code — set the OpenAI base URL:\r
#   base URL = http://127.0.0.1:8765/v1\r
#   API key  = anything (the server is local, no auth)\r
#   model    = any currently-loaded model id (see GET /v1/models)\r
\r
curl http://127.0.0.1:8765/v1/models   # list ids you can put in the IDE\r
\`\`\`\r
`,J='```javascript\r\n// List the model ids you can select in your IDE\r\nconst res = await fetch("http://127.0.0.1:8765/v1/models");\r\nconst models = await res.json();\r\nconsole.log(models.map((m) => m.id));\r\n```\r\n',B=`\`\`\`python\r
# Continue (config.yaml) / any OpenAI-compatible IDE plugin\r
# models:\r
#   - title: "Local weight-streaming"\r
#     provider: "openai"\r
#     model: "default"                 # a loaded model id\r
#     apiBase: "http://127.0.0.1:8765/v1"\r
#     apiKey: "local"                  # not checked\r
\r
import requests\r
print(requests.get("http://127.0.0.1:8765/v1/models", timeout=5).json())\r
\`\`\`\r
`,F=`\`\`\`bash\r
# Create (debug context is merged server-side if omitted)\r
curl -X POST http://127.0.0.1:8765/v1/issues \\\r
  -H "Content-Type: application/json" \\\r
  -d '{"title": "Crash on unload", "description": "Server exits when unloading the last model while a request is in flight.", "severity": "high"}'\r
\r
# List / filter / export\r
curl "http://127.0.0.1:8765/v1/issues?status=open"\r
curl "http://127.0.0.1:8765/v1/issues/export?format=md"\r
\r
# Maintainer: mark fixed (requires root_cause + fix_summary + verify_steps)\r
curl -X PATCH http://127.0.0.1:8765/v1/issues/ISSUE-001 \\\r
  -H "Content-Type: application/json" \\\r
  -d '{"status": "fixed", "root_cause": "use-after-free in manager", "fix_summary": "hold ref until request done", "verify_steps": "unload during a stream, expect no crash"}'\r
\r
# User verification\r
curl -X POST http://127.0.0.1:8765/v1/issues/ISSUE-001/verify \\\r
  -H "Content-Type: application/json" -d '{"verified": true}'\r
\`\`\`\r
`,R=`\`\`\`bash\r
# Scan a folder for GGUF files (recursive; can be slow on big stores)\r
curl "http://127.0.0.1:8765/v1/models/scan?dir=./models"\r
\r
# Load a model by id\r
curl -X POST http://127.0.0.1:8765/v1/models/load \\\r
  -H "Content-Type: application/json" \\\r
  -d '{"model_id": "default", "model_path": "./models/qwen.gguf", "buffer_mb": 64, "n_ctx": 2048}'\r
\r
# List / unload\r
curl http://127.0.0.1:8765/v1/models\r
curl -X POST http://127.0.0.1:8765/v1/models/unload \\\r
  -H "Content-Type: application/json" -d '{"model_id": "default"}'\r
\`\`\`\r
`,X=`\`\`\`bash\r
# Non-streaming\r
curl http://127.0.0.1:8765/v1/generate \\\r
  -H "Content-Type: application/json" \\\r
  -d '{"model": "default", "prompt": "The capital of France is", "max_tokens": 8}'\r
\r
# Streaming (SSE tokens; errors arrive in-stream)\r
curl -N http://127.0.0.1:8765/v1/generate \\\r
  -H "Content-Type: application/json" \\\r
  -d '{"model": "default", "prompt": "Count to 5:", "max_tokens": 16, "stream": true}'\r
\`\`\`\r
`,G=`\`\`\`python\r
import requests\r
\r
with requests.post(\r
    "http://127.0.0.1:8765/v1/generate",\r
    json={"model": "default", "prompt": "Count to 5:", "max_tokens": 16, "stream": True},\r
    stream=True,\r
    timeout=120,\r
) as r:\r
    for line in r.iter_lines(decode_unicode=True):\r
        if line:\r
            print(line)  # SSE token / in-stream error\r
\`\`\`\r
`,z=`\`\`\`bash\r
curl http://127.0.0.1:8765/v1/chat/completions \\\r
  -H "Content-Type: application/json" \\\r
  -d '{\r
    "model": "default",\r
    "messages": [{"role": "user", "content": "Explain mmap in one paragraph."}],\r
    "temperature": 0.7,\r
    "top_p": 1.0,\r
    "max_tokens": 256,\r
    "reasoning_effort": "medium",\r
    "stream": true\r
  }'\r
\`\`\`\r
`,K=`\`\`\`javascript\r
// Streaming over fetch + SSE\r
const res = await fetch("http://127.0.0.1:8765/v1/chat/completions", {\r
  method: "POST",\r
  headers: { "Content-Type": "application/json" },\r
  body: JSON.stringify({\r
    model: "default",\r
    messages: [{ role: "user", content: "Explain mmap in one paragraph." }],\r
    stream: true,\r
    reasoning_effort: "medium", // accepted, NOT executed yet\r
  }),\r
});\r
\r
const reader = res.body.getReader();\r
const dec = new TextDecoder();\r
let buf = "";\r
while (true) {\r
  const { done, value } = await reader.read();\r
  if (done) break;\r
  buf += dec.decode(value, { stream: true });\r
  let i;\r
  while ((i = buf.indexOf("\\n")) !== -1) {\r
    const line = buf.slice(0, i).trim();\r
    buf = buf.slice(i + 1);\r
    if (!line.startsWith("data:")) continue;\r
    const payload = line.slice(5).trim();\r
    if (!payload || payload === "[DONE]") continue;\r
    const delta = JSON.parse(payload).choices?.[0]?.delta?.content ?? "";\r
    process.stdout.write(delta);\r
  }\r
}\r
\`\`\`\r
`,V=`\`\`\`python\r
# Streaming with the OpenAI SDK\r
from openai import OpenAI\r
\r
client = OpenAI(base_url="http://127.0.0.1:8765/v1", api_key="not-used")\r
\r
stream = client.chat.completions.create(\r
    model="default",\r
    messages=[{"role": "user", "content": "Explain mmap in one paragraph."}],\r
    temperature=0.7,\r
    top_p=1.0,\r
    max_tokens=256,\r
    reasoning_effort="medium",  # accepted, NOT executed yet\r
    stream=True,\r
)\r
for chunk in stream:\r
    delta = chunk.choices[0].delta.content or ""\r
    print(delta, end="", flush=True)\r
\`\`\`\r
`,W=`\`\`\`bash\r
curl http://127.0.0.1:8765/v1/chat/completions \\\r
  -H "Content-Type: application/json" \\\r
  -d '{\r
    "model": "default",\r
    "messages": [{"role": "user", "content": "Hello!"}],\r
    "stream": false\r
  }'\r
\`\`\`\r
`,Y=`\`\`\`javascript\r
const res = await fetch("http://127.0.0.1:8765/v1/chat/completions", {\r
  method: "POST",\r
  headers: { "Content-Type": "application/json" },\r
  body: JSON.stringify({\r
    model: "default",\r
    messages: [{ role: "user", content: "Hello!" }],\r
  }),\r
});\r
const data = await res.json();\r
console.log(data.choices[0].message.content);\r
\`\`\`\r
`,Q=`\`\`\`python\r
from openai import OpenAI\r
\r
client = OpenAI(base_url="http://127.0.0.1:8765/v1", api_key="not-used")\r
\r
resp = client.chat.completions.create(\r
    model="default",\r
    messages=[{"role": "user", "content": "Hello!"}],\r
)\r
print(resp.choices[0].message.content)\r
\`\`\`\r
`;l.registerLanguage("python",E);l.registerLanguage("javascript",S);l.registerLanguage("js",S);l.registerLanguage("bash",j);l.registerLanguage("sh",j);l.registerLanguage("json",$);const Z={curl:"cURL",python:"Python",js:"JavaScript"},m=[{key:"quickstart",tabs:["curl","python","js"]},{key:"openai",tabs:["curl","python","js"],notes:["reasoningEffort","tools"]},{key:"anthropic",tabs:["curl","python","js"],notes:["anthropicStream"]},{key:"native",tabs:["curl","python"]},{key:"websocket",notes:["websocket"]},{key:"ide",tabs:["curl","python","js"]},{key:"models",tabs:["curl"]},{key:"issues",tabs:["curl"]},{key:"server"}],ee=Object.assign({"./content/anthropic.curl.md":P,"./content/anthropic.js.md":M,"./content/anthropic.python.md":U,"./content/ide.curl.md":D,"./content/ide.js.md":J,"./content/ide.python.md":B,"./content/issues.curl.md":F,"./content/models.curl.md":R,"./content/native.curl.md":X,"./content/native.python.md":G,"./content/openai.curl.md":z,"./content/openai.js.md":K,"./content/openai.python.md":V,"./content/quickstart.curl.md":W,"./content/quickstart.js.md":Y,"./content/quickstart.python.md":Q}),T={};for(const[o,i]of Object.entries(ee)){const d=o.split("/").pop()??o;T[d]=i}function ne(o,i){const d=T[`${o}.${i}.md`]??"",p=d.match(/```(\w+)?\n([\s\S]*?)```/),u=p?p[2].replace(/\n$/,""):d,_=p?.[1]??i,g=l.getLanguage(_)?_:"";return{highlighted:g?l.highlight(u,{language:g}).value:te(u),raw:u}}function te(o){return o.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;")}function re(o){return o.replace(/```[\s\S]*?```/g," ").replace(/`([^`]+)`/g,"$1").replace(/\[([^\]]+)\]\([^)]+\)/g,"$1").replace(/[*_#>]/g," ").toLowerCase()}function de(){b.value;const o=f(""),i=f({}),d=f(m[0]?.key??""),p=C(null),u=(e,r)=>i.value[e]??r,_=(e,r)=>{i.value={...i.value,[e]:r}},g=O(()=>{const e={};for(const r of m){const a=t(`docs.sections.${r.key}.title`),c=t(`docs.sections.${r.key}.body`);e[r.key]=re(`${a} ${c}`)}return e},[b.value]),h=o.value.trim().toLowerCase(),y=h?m.filter(e=>g[e.key].includes(h)):m;L(()=>{const e=p.current;if(!e)return;const r=Array.from(e.querySelectorAll("[data-doc-section]"));if(!r.length)return;const a=new IntersectionObserver(c=>{for(const s of c)if(s.isIntersecting){const v=s.target.getAttribute("data-doc-section");v&&(d.value=v)}},{rootMargin:"-20% 0px -70% 0px",threshold:0});return r.forEach(c=>a.observe(c)),()=>a.disconnect()},[h]);const w=async e=>{try{await navigator.clipboard?.writeText(e),k("success",t("common.copied"))}catch{k("error",t("chat.copyFailed"))}},x=e=>{p.current?.querySelector(`[data-doc-section="${e}"]`)?.scrollIntoView({behavior:"smooth",block:"start"})};return n("div",{class:"page",children:[n("header",{class:"page__header",children:[n("h1",{class:"page__title",children:[n("span",{"aria-hidden":"true",children:"📖"})," ",t("nav.docs")]}),n("a",{class:"docs__swagger",href:"/docs",target:"_blank",rel:"noopener noreferrer",children:[n(N,{size:14,"aria-hidden":"true"})," ",t("docs.openSwagger")]})]}),n("p",{class:"docs__subtitle",children:t("docs.subtitle")}),n("div",{class:"docs__layout",children:[n("nav",{class:"docs__toc","aria-label":t("docs.toc"),children:[n("div",{class:"docs__search",children:[n(H,{size:14,"aria-hidden":"true"}),n("input",{class:"md-input",type:"search",placeholder:t("docs.search"),value:o.value,onInput:e=>o.value=e.target.value,"aria-label":t("docs.search")})]}),n("ul",{children:m.map(e=>{const r=h?!y.some(a=>a.key===e.key):!1;return n("li",{hidden:r,children:n("button",{type:"button",class:`docs__toc-link${d.value===e.key?" is-on":""}`,onClick:()=>x(e.key),children:t(`docs.sections.${e.key}.title`)})},e.key)})})]}),n("div",{class:"docs__content",ref:p,children:y.length===0?n("p",{class:"dialog-text--dim",children:t("docs.searchNoMatch")}):y.map(e=>{const r=e.tabs??[],a=u(e.key,r[0]),c=r.length?ne(e.key,a):null;return n("section",{class:"docs__section",id:`docs-${e.key}`,"data-doc-section":e.key,children:[n("h2",{children:[n("a",{class:"docs__anchor",href:`#docs-${e.key}`,"aria-hidden":"true",children:"#"})," ",t(`docs.sections.${e.key}.title`)]}),n("div",{class:"docs__md",dangerouslySetInnerHTML:{__html:I(t(`docs.sections.${e.key}.body`))}}),r.length?n("div",{class:"docs__code",children:[n("div",{class:"docs__tabs",role:"tablist","aria-label":t(`docs.sections.${e.key}.title`),children:[r.map(s=>n("button",{type:"button",role:"tab","aria-selected":a===s,class:`docs__tab${a===s?" is-on":""}`,onClick:()=>_(e.key,s),children:Z[s]},s)),n("button",{type:"button",class:"docs__copy",onClick:()=>c&&void w(c.raw),children:t("docs.copyBlock")})]}),n("pre",{class:"codeblock__pre docs__pre",children:n("code",{class:"hljs",dangerouslySetInnerHTML:{__html:c?.highlighted??""}})})]}):null,e.notes?.length?n("div",{class:"docs__notes",children:e.notes.map(s=>n("p",{class:"docs__note",children:[n(A,{label:t("docs.honest")})," ",t(`docs.honestNotes.${s}`)]},s))}):null,e.key==="issues"?n(q,{class:"docs__lifecycle",children:[n("h4",{children:t("docs.lifecycle.title")}),n("p",{class:"dialog-text",children:t("docs.lifecycle.body")})]}):null]},e.key)})})]})]})}export{de as DocsPage};
