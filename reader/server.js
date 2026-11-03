const http = require('http');
const fs = require('fs');
const path = require('path');
const os = require('os');
const { exec } = require('child_process');

const PORT = Number(process.env.PORT || 8765);
const ROOT = __dirname;
const ARTICLE = path.join(ROOT, 'article.json');
const DATA_DIR = path.join(process.env.LOCALAPPDATA || os.homedir(), 'daily-reading');
const STATE = path.join(DATA_DIR, 'state.json');
const SESSIONS = path.join(DATA_DIR, 'sessions');

fs.mkdirSync(SESSIONS, { recursive: true });

const readJSON = (f, fb) => {
  try { return JSON.parse(fs.readFileSync(f, 'utf8')); } catch { return fb; }
};
const writeJSON = (f, obj) => fs.writeFileSync(f, JSON.stringify(obj, null, 2), 'utf8');

const state = readJSON(STATE, { session: Date.now().toString(36), started_at: null, records: [] });
// 给历史记录补 id（老版本写的数据没有 id，删除功能需要）
state.seq = state.seq || 0;
for (const r of state.records) {
  if (!r.id) r.id = ++state.seq;
}
state.seq = Math.max(state.seq, ...state.records.map(r => r.id || 0), 0);

function send(res, code, body, type = 'application/json; charset=utf-8') {
  res.writeHead(code, { 'Content-Type': type, 'Cache-Control': 'no-store' });
  res.end(body);
}

function body(req) {
  return new Promise((resolve, reject) => {
    let raw = '';
    req.on('data', c => {
      raw += c;
      if (raw.length > 2e6) reject(new Error('too large'));
    });
    req.on('end', () => resolve(raw));
    req.on('error', reject);
  });
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://127.0.0.1:${PORT}`);

  try {
    if (req.method === 'GET' && url.pathname === '/api/article') {
      if (!fs.existsSync(ARTICLE)) {
        return send(res, 404, JSON.stringify({ error: '还没有 article.json，先运行 1-提取PDF.bat' }));
      }
      const article = readJSON(ARTICLE, null);
      // 换了文章就自动清空上一轮的记录，避免串台
      if (article && state.title !== article.title) {
        if (state.records.length) {
          const tag = new Date().toISOString().replace(/[:.]/g, '-');
          writeJSON(path.join(SESSIONS, `auto-${tag}.json`), {
            title: state.title || '(untitled)',
            started_at: state.started_at,
            records: state.records,
            note: '换文章时自动归档',
          });
        }
        state.title = article.title;
        state.records = [];
        state.started_at = null;
        writeJSON(STATE, state);
      }
      return send(res, 200, JSON.stringify(article));
    }

    if (req.method === 'GET' && url.pathname === '/api/state') {
      return send(res, 200, JSON.stringify(state));
    }

    if (req.method === 'POST' && url.pathname === '/api/record') {
      const data = JSON.parse((await body(req)) || '{}');
      if (!data.text) return send(res, 400, JSON.stringify({ error: 'empty' }));
      if (!state.started_at) state.started_at = new Date().toISOString();
      const id = ++state.seq;
      state.records.push({
        id,
        text: String(data.text).slice(0, 120),
        para: Number(data.para) || 0,
        page: Number(data.page) || 0,
        block: Number(data.block) || 0,
        at: new Date().toISOString(),
      });
      writeJSON(STATE, state);
      return send(res, 200, JSON.stringify({ ok: true, id, count: state.records.length }));
    }

    // 删掉一条选错的记录
    if (req.method === 'POST' && url.pathname === '/api/delete') {
      const { id } = JSON.parse((await body(req)) || '{}');
      const before = state.records.length;
      state.records = state.records.filter(r => String(r.id) !== String(id));
      if (state.records.length === before) {
        return send(res, 404, JSON.stringify({ error: 'not found' }));
      }
      writeJSON(STATE, state);
      return send(res, 200, JSON.stringify({ ok: true, count: state.records.length }));
    }

    if (req.method === 'POST' && url.pathname === '/api/finish') {
      const article = readJSON(ARTICLE, { title: 'unknown', words: 0 });
      const finished = new Date().toISOString();
      const minutes = state.started_at
        ? Math.round((Date.parse(finished) - Date.parse(state.started_at)) / 60000)
        : 0;
      const payload = {
        title: article.title,
        source: article.source,
        article_words: article.words,
        pages: article.pages,
        article: article.blocks,      // 存全文，换文章后仍可回头分析
        started_at: state.started_at,
        finished_at: finished,
        minutes,
        records: state.records,
      };
      writeJSON(path.join(SESSIONS, `${payload.finished_at.replace(/[:.]/g, '-')}.json`), payload);
      writeJSON(path.join(DATA_DIR, 'last.json'), payload);
      state.session = Date.now().toString(36);
      state.started_at = null;
      state.records = [];
      writeJSON(STATE, state);
      return send(res, 200, JSON.stringify({ ok: true, records: payload.records.length, minutes }));
    }

    if (req.method === 'POST' && url.pathname === '/api/reset') {
      state.records = [];
      state.started_at = null;
      writeJSON(STATE, state);
      return send(res, 200, JSON.stringify({ ok: true }));
    }

    // 静��
    let p = url.pathname === '/' ? '/index.html' : url.pathname;
    const file = path.join(ROOT, path.normalize(p).replace(/^(\.\.[\/\\])+/, ''));
    if (!file.startsWith(ROOT)) return send(res, 403, 'forbidden');
    const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8' };
    if (!fs.existsSync(file)) return send(res, 404, 'not found', 'text/plain');
    return send(res, 200, fs.readFileSync(file), types[path.extname(file)] || 'application/octet-stream');
  } catch (e) {
    return send(res, 500, JSON.stringify({ error: String(e) }));
  }
});

server.listen(PORT, '127.0.0.1', () => {
  const link = `http://127.0.0.1:${PORT}/`;
  console.log(`阅读器已启动: ${link}`);
  console.log('关闭这个窗口即结束。');
  if (process.platform === 'win32' && !process.env.NO_OPEN) exec(`start "" "${link}"`, { shell: 'cmd.exe' });
});
