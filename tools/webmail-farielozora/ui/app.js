/* ---------------------------------------------------------------
   app.js — SPA webmail, tampilan & fitur mengikuti Cloud Mail
   (mail-vue): aside gelap 260px, header cari, list 48px, reader,
   compose panel, dark mode, star, delete, search, folder.

   Tanpa dependensi eksternal: Vue dipinjam dari ./vendor/vue.mjs,
   ikon SVG inline. Tidak butuh importmap / CDN.
   --------------------------------------------------------------- */

import { createApp, reactive, computed, onMounted } from './vendor/vue.mjs'

/* ------------------------------------------------------------- ikon */

const ICONS = {
  inbox: 'M19 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2Zm0 12h-4a3 3 0 0 1-6 0H5V7h14v8Z',
  send: 'M3.4 20.4 21 12 3.4 3.6 3.4 10l12 2-12 2Z',
  draft: 'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Zm0 2.5L17.5 8H14Z',
  trash: 'M9 3v1H4v2h16V4h-5V3Zm-3 5 1 13h10l1-13Z',
  star: 'M12 2.5l2.9 6.1 6.6.9-4.8 4.7 1.2 6.6L12 17.6 6.1 20.8l1.2-6.6L2.5 9.5l6.6-.9Z',
  settings: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Zm9.4 4a7.6 7.6 0 0 1-.1 1.2l2 1.6-2 3.4-2.4-1a7.4 7.4 0 0 1-2 1.2l-.4 2.6h-4l-.4-2.6a7.4 7.4 0 0 1-2-1.2l-2.4 1-2-3.4 2-1.6a7.6 7.6 0 0 1 0-2.4l-2-1.6 2-3.4 2.4 1a7.4 7.4 0 0 1 2-1.2L10.5 2h4l.4 2.6a7.4 7.4 0 0 1 2 1.2l2.4-1 2 3.4-2 1.6c.1.4.1.8.1 1.2Z',
  compose: 'M3 17.3V21h3.7L17.8 9.9l-3.7-3.7Zm19.7-12a1 1 0 0 0 0-1.4l-2.6-2.6a1 1 0 0 0-1.4 0l-1.8 1.8 3.7 3.7Z',
  search: 'M15.5 14h-.8l-.3-.3a6.5 6.5 0 1 0-.7.7l.3.3v.8l5 5 1.5-1.5Zm-6 0a4.5 4.5 0 1 1 0-9 4.5 4.5 0 0 1 0 9Z',
  back: 'M15.4 7.4 14 6l-6 6 6 6 1.4-1.4L10.8 12Z',
  reply: 'M10 9V5l-7 7 7 7v-4c5 0 8.5 1.6 11 5-1-5-4-10-11-11Z',
  forward: 'M14 9V5l7 7-7 7v-4c-5 0-8.5 1.6-11 5 1-5 4-10 11-11Z',
  attach: 'M16.5 6a4.5 4.5 0 0 0-6.4 0l-6.4 6.4a3.2 3.2 0 0 0 4.5 4.5l6.4-6.4a1.8 1.8 0 0 0-2.6-2.6l-5.7 5.7-1.3-1.3 5.7-5.7a3.7 3.7 0 0 1 5.2 5.2l-6.4 6.4a5.3 5.3 0 0 1-7.5-7.5l6.4-6.4A6.4 6.4 0 0 1 18 15.1l-1.3-1.3A4.5 4.5 0 0 0 16.5 6Z',
  close: 'M19 6.4 17.6 5 12 10.6 6.4 5 5 6.4 10.6 12 5 17.6 6.4 19 12 13.4 17.6 19 19 17.6 13.4 12Z',
  reload: 'M12 5V2L7 6.5 12 11V8a5 5 0 1 1-5 5H5a7 7 0 1 0 7-8Z',
  menu: 'M3 6h18v2H3Zm0 5h18v2H3Zm0 5h18v2H3Z',
  check: 'M9 16.2 4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4Z',
  down: 'M7 10l5 5 5-5Z',
  download: 'M12 3v10l3.5-3.5 1.4 1.4L12 16.8 7.1 10.9l1.4-1.4L12 13V3ZM5 19h14v2H5Z',
  dot: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8Z',
}

const Icon = {
  props: { name: { type: String, required: true }, size: { type: [Number, String], default: 20 } },
  setup(props) {
    return () =>
      // eslint-disable-next-line
      h(
        'svg',
        {
          viewBox: '0 0 24 24',
          width: props.size,
          height: props.size,
          fill: 'currentColor',
          'aria-hidden': 'true',
          style: 'display:inline-block;vertical-align:middle;flex-shrink:0',
        },
        [h('path', { d: ICONS[props.name] || ICONS.dot })]
      )
  },
}

/* ------------------------------------------------------------- state */

const store = reactive({
  booted: false,
  user: null,
  folders: [],
  folder: 'INBOX',
  list: [],
  total: 0,
  offset: 0,
  pageSize: 50,
  loading: false,
  noMore: false,
  selected: [],
  current: null,
  view: 'list',
  asideShow: window.innerWidth > 1024,
  isMobile: window.innerWidth <= 1024,
  dark: false,
  search: { active: false, text: '', type: 'subject', applied: '' },
  compose: { open: false, mode: 'new', to: '', cc: '', subject: '', body: '', sending: false },
  ctx: { open: false, x: 0, y: 0, mail: null },
  toasts: [],
})

const FOLDER_LABEL = { INBOX: 'Inbox', Sent: 'Sent', Drafts: 'Drafts', Trash: 'Trash' }

function toast(message, type) {
  const id = Math.random().toString(36).slice(2)
  store.toasts.push({ id: id, message: message, type: type || 'success' })
  setTimeout(() => {
    const i = store.toasts.findIndex((t) => t.id === id)
    if (i > -1) store.toasts.splice(i, 1)
  }, 3000)
}

/* ------------------------------------------------------------- api */

async function api(path, opts = {}) {
  const res = await fetch('/api' + path, {
    credentials: 'same-origin',
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  let data = {}
  try {
    data = await res.json()
  } catch (e) {
    data = {}
  }
  if (!res.ok) {
    const err = new Error(data.message || 'HTTP ' + res.status)
    err.status = res.status
    throw err
  }
  return data
}

const post = (path, body) => api(path, { method: 'POST', body: JSON.stringify(body || {}) })

/* ------------------------------------------------------------- utils */

function escapeHtml(v) {
  return String(v == null ? '' : v)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

function highlight(text, keyword) {
  const src = String(text == null ? '' : text)
  const kw = (keyword || '').trim()
  if (!kw) return escapeHtml(src)
  const re = new RegExp(kw.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'gi')
  let out = ''
  let last = 0
  for (const m of src.matchAll(re)) {
    out += escapeHtml(src.slice(last, m.index))
    out += '<mark class="search-hit">' + escapeHtml(m[0]) + '</mark>'
    last = m.index + m[0].length
  }
  return out + escapeHtml(src.slice(last))
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'Mei', 'Jun', 'Jul', 'Agu', 'Sep', 'Okt', 'Nov', 'Des']
const MONTHS_LONG = ['Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus', 'September', 'Oktober', 'November', 'Desember']

function fmtTime(ms) {
  if (!ms) return ''
  const d = new Date(ms)
  const diff = (Date.now() - d) / 1000
  if (diff < 60) return 'baru saja'
  if (diff < 3600) return Math.floor(diff / 60) + ' menit lalu'
  if (diff < 86400) return Math.floor(diff / 3600) + ' jam lalu'
  if (diff < 86400 * 7) return Math.floor(diff / 86400) + ' hari lalu'
  const sameYear = d.getFullYear() === new Date().getFullYear()
  return d.getDate() + ' ' + MONTHS[d.getMonth()] + (sameYear ? '' : ' ' + d.getFullYear())
}

function fmtDate(ms) {
  if (!ms) return ''
  const d = new Date(ms)
  return (
    d.getDate() + ' ' + MONTHS_LONG[d.getMonth()] + ' ' + d.getFullYear() + ', ' +
    String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0')
  )
}

function fmtBytes(n) {
  const b = Number(n || 0)
  if (b < 1024) return b + ' B'
  if (b < 1048576) return (b / 1024).toFixed(1) + ' KB'
  return (b / 1048576).toFixed(2) + ' MB'
}

function applyTheme() {
  document.documentElement.setAttribute('class', store.dark ? 'dark' : '')
  try {
    localStorage.setItem('ui', JSON.stringify({ dark: store.dark }))
  } catch (e) {}
}

/* ------------------------------------------------------------- actions */

async function loadMe() {
  try {
    store.user = await api('/me')
    return true
  } catch (e) {
    store.user = null
    return false
  }
}

async function loadFolders() {
  try {
    const d = await api('/folders')
    store.folders = d.folders || []
  } catch (e) {}
}

function folderMeta(name) {
  return store.folders.find((f) => f.name === name) || { name: name, total: 0, unread: 0 }
}

async function loadList(reset = true) {
  if (store.loading) return
  store.loading = true
  try {
    if (reset) {
      store.offset = 0
      store.noMore = false
    }
    const q = new URLSearchParams({
      folder: store.folder,
      offset: String(store.offset),
      size: String(store.pageSize),
    })
    const d = await api('/emails?' + q.toString())
    const rows = d.list || []
    store.list = reset ? rows : store.list.concat(rows)
    store.total = d.total || 0
    store.offset = store.list.length
    store.noMore = rows.length < store.pageSize
  } catch (e) {
    if (e.status === 401) store.user = null
    else toast(e.message, 'error')
  } finally {
    store.loading = false
  }
}

async function doSearch() {
  const text = (store.search.text || '').trim()
  if (!text) {
    await resetSearch()
    return
  }
  store.loading = true
  try {
    const q = new URLSearchParams({ q: text, type: store.search.type, folder: store.folder })
    const d = await api('/search?' + q.toString())
    store.list = d.list || []
    store.total = d.total || 0
    store.noMore = true
    store.search.applied = text
    store.search.active = false
    store.view = 'list'
  } catch (e) {
    toast(e.message, 'error')
  } finally {
    store.loading = false
  }
}

async function resetSearch() {
  store.search.text = ''
  store.search.applied = ''
  store.search.active = false
  await loadList(true)
}

async function openMail(mail) {
  closeCtx()
  try {
    const q = new URLSearchParams({ folder: store.folder, uid: mail.uid })
    const d = await api('/email?' + q.toString())
    store.current = d
    store.view = 'content'
    if (d.unread) {
      d.unread = 0
      mail.unread = 0
      post('/read', { folder: store.folder, uids: [mail.uid] }).then(loadFolders)
    }
  } catch (e) {
    toast(e.message, 'error')
  }
}

async function toggleStar(mail, ev) {
  if (ev) ev.stopPropagation()
  if (!mail) return
  const next = mail.isStar ? 0 : 1
  mail.isStar = next
  if (store.current && store.current.uid === mail.uid) store.current.isStar = next
  try {
    await post('/star', { folder: store.folder, uid: mail.uid, star: next })
  } catch (e) {
    mail.isStar = next ? 0 : 1
    toast(e.message, 'error')
  }
}

async function markRead(uids) {
  if (!uids || !uids.length) return
  await post('/read', { folder: store.folder, uids: uids })
  store.list.forEach((m) => {
    if (uids.indexOf(m.uid) > -1) m.unread = 0
  })
  await loadFolders()
}

async function deleteMails(uids) {
  if (!uids || !uids.length) return
  await post('/delete', { folder: store.folder, uids: uids })
  store.list = store.list.filter((m) => uids.indexOf(m.uid) < 0)
  store.total = Math.max(0, store.total - uids.length)
  store.selected = []
  if (store.current && uids.indexOf(store.current.uid) > -1) {
    store.current = null
    store.view = 'list'
  }
  await loadFolders()
  toast('Pesan dihapus')
}

function askDelete(uids) {
  if (!uids || !uids.length) return
  if (window.confirm('Hapus ' + uids.length + ' pesan?')) deleteMails(uids)
}

function toggleSelect(mail) {
  const i = store.selected.indexOf(mail.uid)
  if (i > -1) store.selected.splice(i, 1)
  else store.selected.push(mail.uid)
}

function toggleSelectAll() {
  if (store.selected.length === store.list.length) store.selected = []
  else store.selected = store.list.map((m) => m.uid)
}

async function switchFolder(name) {
  store.folder = name
  store.view = 'list'
  store.current = null
  store.selected = []
  store.search.applied = ''
  store.search.text = ''
  if (store.isMobile) store.asideShow = false
  await loadList(true)
}

function openCompose(mode, mail) {
  const c = store.compose
  c.open = true
  c.mode = mode || 'new'
  c.sending = false
  if (mode === 'reply' && mail) {
    c.to = mail.sendEmail
    c.subject = (mail.subject || '').indexOf('Re:') === 0 ? mail.subject : 'Re: ' + (mail.subject || '')
    c.body = '\n\n--- pesan asli ---\n' + (mail.text || '')
  } else if (mode === 'forward' && mail) {
    c.to = ''
    c.subject = (mail.subject || '').indexOf('Fwd:') === 0 ? mail.subject : 'Fwd: ' + (mail.subject || '')
    c.body = '\n\n--- pesan asli ---\n' + (mail.text || '')
  } else {
    c.to = ''
    c.subject = ''
    c.body = ''
  }
  c.cc = ''
}

async function sendMail() {
  const c = store.compose
  if (!(c.to || '').trim()) {
    toast('Penerima belum diisi', 'error')
    return
  }
  c.sending = true
  try {
    const d = await post('/send', { to: c.to, cc: c.cc, subject: c.subject, body: c.body })
    toast(d.message || 'Pesan terkirim')
    if (d.missing && d.missing.length) toast('Tidak ada mailbox lokal: ' + d.missing.join(', '), 'error')
    c.open = false
    await loadFolders()
    if (store.folder === 'Sent' || store.folder === 'INBOX') await loadList(true)
  } catch (e) {
    toast(e.message, 'error')
  } finally {
    c.sending = false
  }
}

async function logout() {
  try {
    await post('/logout', {})
  } catch (e) {}
  store.user = null
  store.list = []
  store.current = null
  store.view = 'list'
}

function openCtx(ev, mail) {
  ev.preventDefault()
  store.ctx.open = true
  store.ctx.x = Math.min(ev.clientX, window.innerWidth - 210)
  store.ctx.y = Math.min(ev.clientY, window.innerHeight - 240)
  store.ctx.mail = mail
}

function closeCtx() {
  store.ctx.open = false
}

async function bootAfterLogin() {
  await loadFolders()
  store.folder = 'INBOX'
  store.view = 'list'
  await loadList(true)
}

/* ------------------------------------------------------------- login */

const LoginView = {
  setup() {
    const form = reactive({ email: '', password: '', confirm: '', name: '' })
    const error = reactive({ v: '' })
    const loading = reactive({ v: false })
    const mode = reactive({ v: 'login' })
    const cfg = reactive({ domain: 'farielozora.biz.id', register: false, minPassword: 8, maxPerHour: 5 })

    api('/config')
      .then((c) => Object.assign(cfg, c))
      .catch(() => {})

    function switchMode(m) {
      mode.v = m
      error.v = ''
      form.password = ''
      form.confirm = ''
    }

    async function submit() {
      error.v = ''
      const local = form.email.trim()
      if (!local || !form.password) {
        error.v = 'Email dan password wajib diisi.'
        return
      }
      loading.v = true
      try {
        if (mode.v === 'register') {
          const d = await post('/register', {
            email: local,
            password: form.password,
            confirm: form.confirm,
            name: form.name,
          })
          store.user = d.user
        } else {
          const d = await post('/login', {
            email: local.indexOf('@') > -1 ? local : local + '@' + cfg.domain,
            password: form.password,
          })
          store.user = d.user
        }
        await bootAfterLogin()
      } catch (e) {
        error.v = e.message
      } finally {
        loading.v = false
      }
    }

    return { form, error, loading, mode, cfg, submit, switchMode }
  },
  template: `
  <div id="login-box">
    <div id="background-wrap">
      <div class="x1 cloud"></div><div class="x2 cloud"></div><div class="x3 cloud"></div>
      <div class="x4 cloud"></div><div class="x5 cloud"></div>
    </div>
    <div class="form-wrapper">
      <div class="container">
        <span class="form-title">Cloud Mail</span>
        <span class="form-desc">
          {{ mode.v === 'login' ? 'Masuk ke mailbox kamu' : 'Buat mailbox baru di @' + cfg.domain }}
        </span>

        <div class="email-group">
          <input class="field" v-model="form.email" type="text" :placeholder="mode.v === 'login' ? 'Email' : 'Nama mailbox'"
                 autocomplete="off" @keyup.enter="submit" />
          <span class="email-suffix">@{{ cfg.domain }}</span>
        </div>

        <input v-if="mode.v === 'register'" class="field" v-model="form.name"
               type="text" placeholder="Nama tampilan (opsional)" autocomplete="off" />

        <input class="field" v-model="form.password" type="password"
               :placeholder="mode.v === 'register' ? 'Password (min ' + cfg.minPassword + ' karakter)' : 'Password'"
               autocomplete="off" @keyup.enter="submit" />

        <input v-if="mode.v === 'register'" class="field" v-model="form.confirm" type="password"
               placeholder="Ulangi password" autocomplete="off" @keyup.enter="submit" />

        <div class="login-error" v-if="error.v">{{ error.v }}</div>

        <button class="btn primary full" :disabled="loading.v" @click="submit">
          {{ loading.v ? 'Memproses...' : (mode.v === 'login' ? 'Masuk' : 'Daftar') }}
        </button>

        <div class="login-switch" v-if="cfg.register">
          <template v-if="mode.v === 'login'">
            Belum punya akun?
            <a href="#" @click.prevent="switchMode('register')">Daftar sekarang</a>
          </template>
          <template v-else>
            Sudah punya akun?
            <a href="#" @click.prevent="switchMode('login')">Masuk</a>
          </template>
        </div>
      </div>
    </div>
  </div>
  `,
}

/* ------------------------------------------------------------- aside */

const AsideBar = {
  components: { Icon },
  setup() {
    return { store, switchFolder, folderMeta, openCompose, FOLDER_LABEL }
  },
  template: `
  <div class="aside-inner">
    <div class="brand">
      <div class="logo">&#9993;</div>
      <span>Cloud Mail</span>
    </div>
    <button class="compose-bar" type="button" @click="openCompose('new')">
      <Icon name="compose" :size="20" />
      <span>Compose</span>
    </button>
    <div class="menu-item" :class="{active: store.view !== 'settings' && store.folder === 'INBOX'}"
         @click="switchFolder('INBOX')">
      <Icon name="inbox" :size="20" />
      <span class="menu-name">Inbox</span>
      <span class="badge" v-if="folderMeta('INBOX').unread">{{ folderMeta('INBOX').unread }}</span>
    </div>
    <div class="menu-item" :class="{active: store.view !== 'settings' && store.folder === 'Sent'}"
         @click="switchFolder('Sent')">
      <Icon name="send" :size="19" />
      <span class="menu-name">Sent</span>
    </div>
    <div class="menu-item" :class="{active: store.view !== 'settings' && store.folder === 'Drafts'}"
         @click="switchFolder('Drafts')">
      <Icon name="draft" :size="19" />
      <span class="menu-name">Drafts</span>
    </div>
    <div class="menu-item" :class="{active: store.view !== 'settings' && store.folder === 'Trash'}"
         @click="switchFolder('Trash')">
      <Icon name="trash" :size="17" />
      <span class="menu-name">Trash</span>
    </div>
    <div class="menu-item" :class="{active: store.view === 'settings'}" @click="store.view='settings'">
      <Icon name="settings" :size="19" />
      <span class="menu-name">Settings</span>
    </div>
  </div>
  `,
}

/* ------------------------------------------------------------- list */

const ListView = {
  components: { Icon },
  setup() {
    const highlightText = computed(() => store.search.applied)
    const allChecked = computed(
      () => store.list.length > 0 && store.selected.length === store.list.length
    )
    function rowHtml(m, field) {
      return highlight(m[field] || '', highlightText.value)
    }
    function onScroll(e) {
      const el = e.target
      if (el.scrollTop + el.clientHeight >= el.scrollHeight - 300 && !store.noMore) loadList(false)
    }
    return {
      store, rowHtml, fmtTime, openMail, toggleStar, toggleSelect, toggleSelectAll,
      allChecked, askDelete, markRead, onScroll, openCtx, openCompose, closeCtx, loadList,
      toggleSelectAllClick: toggleSelectAll,
    }
  },
  template: `
  <div class="list-wrap" @click="closeCtx">
    <div class="list-actions">
      <label class="cb-wrap" @click.stop>
        <input type="checkbox" :checked="allChecked" :disabled="!store.list.length"
               @change="toggleSelectAll" />
      </label>
      <div class="left">
        <span class="icon-btn" title="Muat ulang" @click="loadList(true)">
          <Icon name="reload" :size="18" />
        </span>
        <span class="icon-btn" v-if="store.selected.length" title="Hapus"
              @click="askDelete(store.selected.slice())">
          <Icon name="trash" :size="16" />
        </span>
        <span class="icon-btn" v-if="store.selected.length" title="Tandai dibaca"
              @click="markRead(store.selected.slice()); store.selected = []">
          <Icon name="check" :size="18" />
        </span>
      </div>
      <div class="right">
        <span class="email-count" v-if="store.total">{{ store.total }} pesan</span>
      </div>
    </div>

    <div class="list-scroll" @scroll="onScroll">
      <div v-if="store.loading && !store.list.length" class="skeleton-box">
        <div class="sk-row" v-for="n in 8" :key="n"></div>
      </div>
      <div class="empty-box" v-else-if="!store.list.length">
        <div class="empty-inner">
          <div class="empty-icon">&#128235;</div>
          <div>Tidak ada pesan</div>
        </div>
      </div>
      <div v-for="m in store.list" :key="m.uid" class="email-row"
           :class="{'right-checked': store.ctx.open && store.ctx.mail && store.ctx.mail.uid === m.uid}"
           @click="openMail(m)" @contextmenu="openCtx($event, m)">
        <div class="cb" @click.stop>
          <label class="cb-wrap">
            <input type="checkbox" :checked="store.selected.indexOf(m.uid) > -1"
                   @change="toggleSelect(m)" />
          </label>
        </div>
        <div class="star-wrap" @click.stop="toggleStar(m, $event)">
          <span :class="{starred: m.isStar}"><Icon name="star" :size="17" /></span>
        </div>
        <div class="title">
          <div class="sender">
            <span class="name" :class="{'bold': m.unread}" v-html="rowHtml(m, 'name')"></span>
            <span class="phone-time">{{ fmtTime(m.createTime) }}</span>
          </div>
          <div class="email-text">
            <span class="email-subject" :class="{'bold': m.unread}">
              <i class="unread" v-if="m.unread"></i>
              <span v-html="rowHtml(m, 'subject')"></span>
            </span>
            <span class="email-content" v-html="rowHtml(m, 'listText')"></span>
          </div>
        </div>
        <div class="right">
          <span :class="{'bold': m.unread}">{{ fmtTime(m.createTime) }}</span>
        </div>
      </div>
      <div class="load-more" v-if="store.list.length && !store.noMore" @click="loadList(false)">
        memuat lagi...
      </div>
    </div>

    <div v-if="store.ctx.open" class="ctx-menu"
         :style="{left: store.ctx.x + 'px', top: store.ctx.y + 'px'}" @click.stop>
      <div class="ctx-item" v-if="store.ctx.mail && store.ctx.mail.unread"
           @click="markRead([store.ctx.mail.uid]); closeCtx()">
        <Icon name="check" :size="17" /><span>Tandai dibaca</span>
      </div>
      <div class="ctx-item" @click="openCompose('reply', store.ctx.mail); closeCtx()">
        <Icon name="reply" :size="17" /><span>Balas</span>
      </div>
      <div class="ctx-item" @click="openCompose('forward', store.ctx.mail); closeCtx()">
        <Icon name="forward" :size="17" /><span>Teruskan</span>
      </div>
      <div class="ctx-item" @click="toggleStar(store.ctx.mail, $event); closeCtx()">
        <Icon name="star" :size="17" /><span>Bintang</span>
      </div>
      <div class="ctx-item danger" @click="askDelete([store.ctx.mail.uid]); closeCtx()">
        <Icon name="trash" :size="16" /><span>Hapus</span>
      </div>
    </div>
  </div>
  `,
}

/* ------------------------------------------------------------- reader */

const ReaderView = {
  components: { Icon },
  setup() {
    function back() {
      store.view = 'list'
      store.current = null
    }
    function onFrameLoad(e) {
      const f = e.target
      try {
        const h = f.contentDocument.documentElement.scrollHeight
        f.style.height = Math.max(320, h + 20) + 'px'
      } catch (err) {}
    }
    function frameDoc() {
      const c = store.current
      if (!c) return ''
      if (c.content) return c.content
      return '<pre style="white-space:pre-wrap;font-family:inherit">' + escapeHtml(c.text || '') + '</pre>'
    }
    function attachHref(a) {
      return '/api/attach?folder=' + encodeURIComponent(store.folder) +
        '&uid=' + encodeURIComponent(store.current.uid) + '&idx=' + a.idx
    }
    return {
      store, back, onFrameLoad, frameDoc, fmtDate, fmtBytes,
      toggleStar, askDelete, openCompose, attachHref,
    }
  },
  template: `
  <div class="reader" v-if="store.current">
    <div class="reader-actions">
      <span class="icon-btn" title="Kembali" @click="back"><Icon name="back" :size="20" /></span>
      <span class="icon-btn" title="Hapus" @click="askDelete([store.current.uid])">
        <Icon name="trash" :size="16" />
      </span>
      <span class="icon-btn" title="Bintang" @click="toggleStar(store.current, $event)">
        <span :class="{starred: store.current.isStar}"><Icon name="star" :size="18" /></span>
      </span>
      <span class="icon-btn" title="Balas" @click="openCompose('reply', store.current)">
        <Icon name="reply" :size="18" />
      </span>
      <span class="icon-btn" title="Teruskan" @click="openCompose('forward', store.current)">
        <Icon name="forward" :size="18" />
      </span>
    </div>
    <div class="reader-body">
      <div class="email-title">{{ store.current.subject }}</div>
      <div class="email-info">
        <div class="send">
          <span class="send-source">From</span>
          <div class="send-name">
            <span class="send-name-title">{{ store.current.name }}</span>
            <span class="send-email">&lt;{{ store.current.sendEmail }}&gt;</span>
          </div>
        </div>
        <div class="receive">
          <span class="source">Recipient</span>
          <span class="receive-email">{{ store.current.toEmail }}</span>
        </div>
        <div class="date">{{ fmtDate(store.current.createTime) }}</div>
      </div>
      <iframe class="htm-frame" sandbox="allow-same-origin" referrerpolicy="no-referrer"
              @load="onFrameLoad" :srcdoc="frameDoc()"></iframe>
      <div class="att" v-if="store.current.attList && store.current.attList.length">
        <div class="att-title">
          <span>Attachments</span><span>({{ store.current.attList.length }})</span>
        </div>
        <div class="att-item" v-for="a in store.current.attList" :key="a.idx">
          <Icon name="attach" :size="18" />
          <span class="att-name">{{ a.filename }}</span>
          <span class="att-size">{{ fmtBytes(a.size) }}</span>
          <a :href="attachHref(a)" download><Icon name="download" :size="20" /></a>
        </div>
      </div>
    </div>
  </div>
  <div v-else class="empty-box"><div class="empty-inner"><div>Pilih pesan</div></div></div>
  `,
}

/* ------------------------------------------------------------- compose */

const ComposeBox = {
  components: { Icon },
  setup() {
    function close() {
      store.compose.open = false
    }
    return { store, close, sendMail }
  },
  template: `
  <div class="write-box" v-if="store.compose.open">
    <div class="title">
      <div class="title-left">
        <Icon name="compose" :size="20" />
        <span class="sender">Sender:</span>
        <span class="sender-name">{{ store.user ? store.user.email : '' }}</span>
      </div>
      <span class="icon-btn" @click="close"><Icon name="close" :size="20" /></span>
    </div>
    <div class="container">
      <input class="field" v-model="store.compose.to" placeholder="Recipient" />
      <input class="field" v-model="store.compose.cc" placeholder="Cc (opsional)" />
      <input class="field" v-model="store.compose.subject" placeholder="Subject" />
      <textarea class="body-input" v-model="store.compose.body" placeholder="Tulis pesan..."></textarea>
      <div class="button-item">
        <button class="btn primary" :disabled="store.compose.sending" @click="sendMail">
          {{ store.compose.sending ? 'Mengirim...' : 'Kirim' }}
        </button>
        <button class="btn" @click="close">Batal</button>
      </div>
    </div>
  </div>
  `,
}

/* ------------------------------------------------------------- settings */

const SettingsView = {
  components: { Icon },
  setup() {
    return { store, logout, applyTheme }
  },
  template: `
  <div class="settings-page">
    <h2>Settings</h2>
    <div class="setting-card">
      <div class="setting-row">
        <div>
          <div class="setting-label">Dark mode</div>
          <div class="setting-desc">Tema gelap untuk seluruh antarmuka</div>
        </div>
        <label class="switch">
          <input type="checkbox" :checked="store.dark"
                 @change="store.dark = $event.target.checked; applyTheme()" />
          <span class="slider"></span>
        </label>
      </div>
    </div>
    <div class="setting-card">
      <div class="setting-row">
        <div>
          <div class="setting-label">Akun</div>
          <div class="setting-desc">{{ store.user ? store.user.email : '' }}</div>
        </div>
        <button class="btn" @click="logout">Logout</button>
      </div>
    </div>
  </div>
  `,
}

/* ------------------------------------------------------------- search */

const SearchDialog = {
  components: { Icon },
  setup() {
    const options = [
      { label: 'Subjek', type: 'subject' },
      { label: 'Isi pesan', type: 'content' },
      { label: 'Pengirim', type: 'sender' },
    ]
    return { store, options, doSearch, resetSearch }
  },
  template: `
  <div class="dialog-mask" v-if="store.search.active" @click.self="store.search.active = false">
    <div class="dialog">
      <div class="dialog-title">Cari pesan</div>
      <input class="field" v-model="store.search.text" placeholder="Kata kunci"
             @keyup.enter="doSearch" />
      <div class="seg-label">Cari di</div>
      <div class="segmented">
        <button v-for="o in options" :key="o.type" class="seg-btn"
                :class="{active: store.search.type === o.type}"
                @click="store.search.type = o.type">{{ o.label }}</button>
      </div>
      <div class="dialog-actions">
        <button class="btn" @click="resetSearch">Reset</button>
        <button class="btn primary" @click="doSearch">Cari</button>
      </div>
    </div>
  </div>
  `,
}

/* ------------------------------------------------------------- shell */

const Shell = {
  components: { Icon, AsideBar, ListView, ReaderView, SettingsView, ComposeBox, SearchDialog },
  setup() {
    function toggleAside() {
      store.asideShow = !store.asideShow
    }
    const title = computed(() => {
      if (store.view === 'settings') return 'Settings'
      return FOLDER_LABEL[store.folder] || store.folder
    })
    const initial = computed(() => {
      const e = store.user && store.user.email ? store.user.email : '?'
      return e[0].toUpperCase()
    })
    function doLogout() {
      logout()
    }
    return { store, toggleAside, title, initial, doLogout, openCompose }
  },
  template: `
  <div class="layout">
    <aside class="aside" :class="store.asideShow ? '' : 'aside-hide'">
      <AsideBar />
    </aside>
    <div class="overlay" v-if="store.asideShow && store.isMobile" @click="store.asideShow = false"></div>
    <div class="main-container">
      <div class="topbar">
        <span class="icon-btn" @click="toggleAside"><Icon name="menu" :size="21" /></span>
        <span class="breadcrumb-item">{{ title }}</span>
        <div class="search-placeholder" :class="{'has-search-text': store.search.applied}"
             @click="store.search.active = true">
          <Icon name="search" :size="18" />
          <span>{{ store.search.applied || 'Cari email' }}</span>
        </div>
        <div class="avatar-wrap">
          <div class="avatar" @click="store.view = 'settings'">
            <div class="avatar-text">{{ initial }}</div>
            <Icon name="down" :size="18" />
          </div>
        </div>
      </div>
      <div class="main-view">
        <SettingsView v-if="store.view === 'settings'" />
        <ReaderView v-else-if="store.view === 'content'" />
        <ListView v-else />
      </div>
    </div>
    <ComposeBox />
    <SearchDialog />
    <div class="toasts">
      <div v-for="t in store.toasts" :key="t.id" class="toast" :class="t.type">{{ t.message }}</div>
    </div>
  </div>
  `,
}

/* ------------------------------------------------------------- root */

const App = {
  components: { LoginView, Shell },
  setup() {
    try {
      const ui = JSON.parse(localStorage.getItem('ui') || '{}')
      store.dark = !!ui.dark
    } catch (e) {}
    onMounted(async () => {
      const el = document.getElementById('loading-first')
      if (el) {
        el.classList.add('loading-hide')
        setTimeout(() => el.remove(), 300)
      }
      store.booted = true
      await loadMe()
      if (store.user) await bootAfterLogin()
      window.addEventListener('resize', () => {
        store.isMobile = window.innerWidth <= 1024
      })
      window.addEventListener('click', closeCtx)
      window.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
          if (store.ctx.open) closeCtx()
          else if (store.compose.open) store.compose.open = false
          else if (store.search.active) store.search.active = false
          else if (store.view === 'content') {
            store.view = 'list'
            store.current = null
          }
        }
      })
    })
    return { store }
  },
  template: `
  <Shell v-if="store.user" />
  <LoginView v-else-if="store.booted" />
  `,
}

const app = createApp(App)
app.component('Icon', Icon)
app.mount('#app')
