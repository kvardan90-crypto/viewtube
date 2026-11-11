const main = document.querySelector("#main");
const menu = document.querySelector("#menu");
const nav = document.querySelector("#nav");
const query = document.querySelector("#query");
const scrim = document.querySelector("#nav-scrim");
const mobile = matchMedia("(max-width: 900px)");
let user = null;
let revision = 0;
let toastTimer;

const paths = {
  menu:"M4 6h16M4 12h16M4 18h16", search:"m20 20-4-4m2-5a7 7 0 1 1-14 0 7 7 0 0 1 14 0Z",
  home:"m3 10 9-7 9 7v10h-6v-6H9v6H3Z", subs:"M3 8h18v12H3zM5 5h14m-12-3h10m3 11-5-3v6z",
  channel:"M4 21v-3c0-5 16-5 16 0v3M16 7a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z",
  plus:"M12 4v16M4 12h16", shield:"M12 22C6 19 4 15 4 11V5l8-3 8 3v6c0 4-2 8-8 11Zm-3-10 2 2 4-4",
  logout:"M11 4H4v16h7m3-12 4 4-4 4M8 12h12", tech:"M3 4h18v13H3zM8 21h8m-4-4v4",
  nature:"M12 21v-7M5 4c6 0 7 3 7 10C5 14 3 9 5 4Zm14 0c2 5 0 10-7 10 0-7 1-10 7-10Z",
  travel:"m3 12 18-9-6 18-4-7-8-2Z", food:"M5 3v6a3 3 0 0 0 6 0V3M8 3v19m12 0V3c-4 3-4 8 0 10",
  music:"M9 18V5l11-2v13M9 18c0 2-5 3-5 1s5-3 5-1Zm11-2c0 2-5 3-5 1s5-3 5-1Z",
  art:"M4 19c0-3 5-4 6-2 1 3-4 5-7 4Zm5-4 8-12 4 4-10 10",
  play:"m9 5 12 7-12 7z", like:"M7 10 12 3c2 0 3 2 2 4l-1 3h6c2 0 2 1 2 2l-2 7c0 1-1 2-2 2H7m0-11H3v11h4z",
  upload:"M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6",
  link:"M10 13a4 4 0 0 0 6 1l4-4a4 4 0 0 0-6-6l-2 2m2 5a4 4 0 0 0-6-1l-4 4a4 4 0 0 0 6 6l2-2",
  theater:"M3 5h18v14H3zM3 16h18",
  lock:"M6 10h12v10H6zM8 10V7a4 4 0 0 1 8 0v3m-4 4v2",
  clock:"M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Zm-10-6v6l4 2",
  warning:"m12 3 10 18H2L12 3Zm0 6v5m0 3v.5",
};
const categories = [
  ["", "Все", "home"], ["Technology", "Технологии", "tech"], ["Nature", "Природа", "nature"],
  ["Travel", "Путешествия", "travel"], ["Cooking", "Кулинария", "food"],
  ["Music", "Музыка", "music"], ["Art", "Творчество", "art"], ["Other", "Другое", "play"],
];
const statusNames = {queued:"В очереди",processing:"Обрабатывается",failed:"Ошибка обработки",hidden:"Скрыто модератором",private:"Приватное видео",open:"На рассмотрении",dismissed:"Отклонена",restored:"Видео восстановлено"};
const numbers = new Intl.NumberFormat("ru-RU", {notation:"compact"});
const dates = new Intl.DateTimeFormat("ru-RU", {dateStyle:"medium"});
const relative = new Intl.RelativeTimeFormat("ru-RU", {numeric:"auto"});

function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  const path = document.createElementNS(svg.namespaceURI, "path");
  svg.setAttribute("viewBox","0 0 24 24");
  svg.setAttribute("aria-hidden","true");
  svg.setAttribute("class","icon");
  for (const [k,v] of Object.entries({d:paths[name],fill:"none",stroke:"currentColor","stroke-width":"1.65","stroke-linecap":"round","stroke-linejoin":"round"})) path.setAttribute(k,v);
  svg.append(path);
  return svg;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key,value] of Object.entries(attrs)) {
    if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value !== false && value != null) node.setAttribute(key, value === true ? "" : value);
  }
  node.append(...children.flat(Infinity).filter(child => child != null && child !== false));
  return node;
}

function href(page, id = "", params = {}) {
  const search = new URLSearchParams(params).toString();
  return "#/" + page + (id ? "/" + encodeURIComponent(id) : "") + (search ? "?" + search : "");
}
const channelUrl = handle => href("channel", handle);
const watchUrl = id => href("watch", id);
const endpoint = id => "/api/videos/" + encodeURIComponent(id);
const channelApi = handle => "/api/channels/" + encodeURIComponent(handle);
const pill = (label, link, className = "") => el("a",{class:"button " + className,href:link},label);
const action = (label, click, className = "") => el("button",{class:"button " + className,type:"button",onclick:click},label);
const notice = (...contents) => el("div",{class:"notice",role:"status"},...contents);
const field = (label, input) => el("label",{},label,input);
const avatar = (handle, size = "") => el("span",{class:"avatar a" + handle.charCodeAt(0)%6 + " " + size,"aria-hidden":"true"},handle.slice(0,1).toUpperCase());
const note = (message) => {
  const toast = document.querySelector("#toast");
  toast.textContent = message;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {toast.textContent = "";},4000);
};

async function api(url, method = "GET", data) {
  const response = await fetch(url, {
    method, headers:data === undefined ? {} : {"Content-Type":"application/json"},
    body:data === undefined ? undefined : JSON.stringify(data),
  });
  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    const fallback = response.status >= 500 ? "Сервис временно недоступен" : "Проверьте введённые данные";
    const error = new Error(typeof payload?.detail === "string" ? payload.detail : fallback);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function guard() {
  if (user) return true;
  location.hash = href("login", "", {next:location.hash.slice(1) || "/"});
  return false;
}

function mutate(url, method, data, message, update = render) {
  return async event => {
    if (!guard()) return;
    const button = event.currentTarget;
    button.disabled = true;
    try {
      const result = await api(url,method,data);
      if (message) note(message);
      if (update) await update(result);
    } catch (error) { note(error.message); }
    finally { button.disabled = false; }
  };
}

function formAction(work) {
  return async event => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector("button[type=submit]");
    const status = form.querySelector(".status");
    status.textContent = "";
    button.disabled = true;
    try { await work(form); }
    catch (error) { status.textContent = error.message; }
    finally { button.disabled = false; }
  };
}
const submit = label => el("button",{class:"button primary",type:"submit"},label);
const feedback = () => el("p",{class:"status",role:"status"});
const input = (name, attrs = {}) => el("input",{name,required:true,...attrs});
const date = value => new Date(value.endsWith("Z") || /[+-]\d\d:\d\d$/.test(value) ? value : value + "Z");
function age(value) {
  const days = Math.max(0,Math.floor((Date.now()-date(value))/86400000));
  for (const [unit, amount] of [["year",365],["month",30],["week",7],["day",1]]) {
    if (days >= amount) return relative.format(-Math.floor(days/amount),unit);
  }
  return "сегодня";
}
function duration(seconds) {
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor(seconds / 60) % 60;
  const tail = String(seconds % 60).padStart(2,"0");
  return hours ? hours + ":" + String(minutes).padStart(2,"0") + ":" + tail : minutes + ":" + tail;
}

function card(video) {
  const title = el("a",{class:"card-title",href:watchUrl(video.id)},video.title);
  const ready = video.state === "ready";
  const state = video.hidden ? "hidden" : video.state;
  const poster = ready ? el("img",{src:endpoint(video.id)+"/poster",alt:"",loading:"lazy",decoding:"async",onerror:event => {
    event.currentTarget.replaceWith(el("span",{class:"placeholder"},icon("play")));
  }}) : el("span",{class:"placeholder"},
    icon(video.state === "failed" ? "warning" : "clock"),statusNames[state] || state);
  return el("article",{class:"card"},
    el("a",{class:"thumb",href:watchUrl(video.id),"aria-hidden":"true",tabindex:"-1"},
      poster,
      ready && el("span",{class:"duration"},duration(video.duration))),
    el("div",{class:"card-info"},avatar(video.owner),
      el("div",{},title,el("div",{class:"meta"},el("a",{href:channelUrl(video.owner)},"@"+video.owner)),
        el("div",{class:"meta"},(video.hidden ? "Скрыто · " : video.visibility === "private" ? "Приватное · " : "")+
          numbers.format(video.views)+" просм. · "+age(video.created)))));
}

const grid = (videos, empty = "Видео пока нет") => videos.length ? el("div",{class:"grid"},videos.map(card)) : notice(empty);
function pageMore(base, params, count, step) {
  const offset = Number(params.get("offset")) || 0;
  const previous = offset > 0;
  const next = count === step && offset + step <= 10000;
  if (!previous && !next) return null;
  const pageLink = value => base + "?" + new URLSearchParams({...Object.fromEntries(params),offset:value});
  return el("nav",{class:"pagination","aria-label":"Страницы результатов"},
    previous ? pill("Назад",pageLink(Math.max(0,offset-step))) : null,
    el("span",{class:"muted"},"Страница "+(Math.floor(offset/step)+1)),
    next ? pill("Далее",pageLink(offset+step)) : null);
}

function navItem(name, label, url, active = false) {
  return el("a",{href:url,class:active?"active":"","aria-current":active?"page":null},icon(name),el("span",{},label));
}

function shell(page, id, params, navigating) {
  const cat = params.get("category") || "";
  if (navigating || document.activeElement !== query) query.value = page === "search" ? params.get("q") || "" : "";
  const account = document.querySelector("#account");
  account.replaceChildren(
    el("a",{class:"button",href:href("upload"),"aria-label":"Создать видео"},icon("plus"),el("span",{class:"label"},"Создать")),
    user ? el("a",{href:channelUrl(user.handle),title:"Мой канал","aria-label":"Мой канал"},avatar(user.handle)) :
      el("a",{class:"button outline",href:href("login")},icon("channel"),el("span",{},"Войти")),
  );
  nav.replaceChildren(
    navItem("home","Главная",href(""),!page && !cat),
    navItem("subs","Подписки",href("subscriptions"),page==="subscriptions"),
    navItem("channel","Мой канал",user?channelUrl(user.handle):href("login"),page==="channel" && id===user?.handle),
    el("hr"),el("h2",{},"Категории"),
    ...categories.slice(1).map(([key,label,ic]) => navItem(ic,label,href("","",{category:key}),cat===key)),
    el("hr"),
    user && ["moderator","admin"].includes(user.role) ? navItem("shield","Модерация",href("moderation"),page==="moderation") : document.createTextNode(""),
    user?.role === "admin" ? navItem("shield","Роли пользователей",href("admin"),page==="admin") : document.createTextNode(""),
    user ? el("button",{type:"button",onclick:async () => {
      try {await api("/api/logout","POST"); user=null; goHome();} catch (error) {note(error.message);}
    }},icon("logout"),"Выйти") : navItem("channel","Войти",href("login"),page==="login"),
  );
}

function goHome() {
  query.value = "";
  if (location.hash === "#/" || !location.hash) render();
  else location.hash = "#/";
}

async function feedPage(page, params) {
  const cat = params.get("category") || "";
  if (page === "subscriptions" && !user) return notice("Войдите, чтобы увидеть новые видео из подписок. ",pill("Войти",href("login","",{next:"/subscriptions"})));
  const filters = new URLSearchParams();
  for (const key of ["category","q","offset"]) if (params.has(key)) filters.set(key,params.get(key));
  if (page === "subscriptions") filters.set("subscriptions","true");
  const videos = await api("/api/videos?"+filters);
  const heading = page === "search" ? el("h1",{class:"results-title"},"Результаты по запросу «"+(params.get("q") || "")+"»") :
    page === "subscriptions" ? el("h1",{},"Подписки") :
      el("nav",{class:"chips","aria-label":"Фильтры ленты"},
        categories.map(([key,label]) => el("a",{
          class:"chip"+(key===cat?" active":""),
          "aria-current":key===cat?"page":null,
          href:href("","",key?{category:key}:{}),
        },label)));
  const empty = page === "search" ? "По вашему запросу ничего не найдено" :
    page === "subscriptions" ? "Здесь появятся новые видео каналов, на которые вы подпишетесь" : "В этой ленте пока нет видео";
  return [heading,grid(videos,empty),
    pageMore(href(page),params,videos.length,24)];
}

async function authPage(page, params) {
  const register = page === "register";
  const next = params.get("next") || "/";
  const safeNext = next.startsWith("/") && !next.startsWith("//") ? next : "/";
  const form = el("form",{class:"panel auth stack",onsubmit:formAction(async form => {
    user = await api("/api/"+page,"POST",Object.fromEntries(new FormData(form)));
    if (location.hash === "#"+safeNext) render();
    else location.hash = "#"+safeNext;
  })},
    el("h1",{},register?"Создать аккаунт":"Вход в ViewTube"),
    field("Имя пользователя",input("handle",{pattern:"[a-zA-Z0-9_]{3,32}",autocomplete:"username",placeholder:"Например, video_lab"})),
    field("Пароль",input("password",{type:"password",minlength:10,maxlength:128,autocomplete:register?"new-password":"current-password"})),
    feedback(),el("div",{class:"row"},submit(register?"Зарегистрироваться":"Войти"),
      pill(register?"Уже есть аккаунт":"Создать аккаунт",href(register?"login":"register","",{next:safeNext}),"outline")));
  return form;
}

function uploadRequest(url, file, onProgress, signal) {
  return new Promise((resolve,reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST",url);
    xhr.responseType = "json";
    xhr.setRequestHeader("Content-Type","application/octet-stream");
    xhr.upload.onprogress = event => {
      if (event.lengthComputable) onProgress(Math.floor(100*event.loaded/event.total));
    };
    xhr.onload = () => xhr.status === 202 ? resolve(xhr.response) :
      reject(new Error(typeof xhr.response?.detail === "string" ? xhr.response.detail : "Не удалось загрузить видео"));
    xhr.onerror = () => reject(new Error("Соединение прервано"));
    xhr.onabort = () => reject(new Error("Передача отменена"));
    const abort = () => xhr.abort();
    signal.addEventListener("abort",abort,{once:true});
    xhr.onloadend = () => signal.removeEventListener("abort",abort);
    xhr.send(file);
  });
}

function uploadPage() {
  if (!user) return notice("Для загрузки видео нужен аккаунт. ",pill("Войти",href("login","",{next:"/upload"}),"outline"));
  let file = null;
  let controller;
  const chooser = input("file",{type:"file",accept:"video/*,.mkv,.avi,.mov",required:false,class:"visually-hidden"});
  const fileName = el("span",{class:"upload-name"},"Выберите видео или перетащите сюда");
  const fileInfo = el("small",{},"MP4, MOV, MKV или WebM, до 256 МБ");
  const progress = el("progress",{max:100,value:0,"aria-label":"Прогресс загрузки"});
  const stage = el("p",{class:"progress-label",role:"status"});
  const percentage = el("span",{"aria-hidden":"true"});
  const cancel = action("Отменить передачу",() => controller?.abort());
  const progressRow = el("div",{class:"upload-progress",hidden:true},progress,
    el("div",{class:"row"},stage,percentage),cancel);
  const send = submit("Загрузить");
  send.disabled = true;
  const drop = el("label",{class:"upload-drop"},
    chooser,el("span",{class:"upload-icon"},icon("upload")),fileName,fileInfo);
  const sizeFormat = new Intl.NumberFormat("ru-RU",{maximumFractionDigits:1});
  function selectFile(selected) {
    if (controller) return;
    file = selected;
    status.textContent = "";
    fileName.textContent = file?.name || "Выберите видео или перетащите сюда";
    fileInfo.textContent = file ? sizeFormat.format(file.size / 1024 / 1024) + " МБ" : "MP4, MOV, MKV или WebM, до 256 МБ";
    send.disabled = !file?.size || file.size > 256*1024*1024;
    if (file && send.disabled) status.textContent = "Выберите непустой файл размером до 256 МБ";
  }
  chooser.addEventListener("change",() => selectFile(chooser.files[0]));
  drop.addEventListener("dragover",event => {
    event.preventDefault();
    if (!controller) drop.classList.add("dragging");
  });
  drop.addEventListener("dragleave",event => {
    if (!drop.contains(event.relatedTarget)) drop.classList.remove("dragging");
  });
  drop.addEventListener("drop",event => {
    event.preventDefault();
    drop.classList.remove("dragging");
    if (!controller) {
      chooser.value = "";
      selectFile(event.dataTransfer.files[0]);
    }
  });
  const status = feedback();
  return el("form",{class:"panel sheet upload-sheet stack",onsubmit:formAction(async form => {
    const data = new FormData(form);
    if (!file?.size || file.size > 256*1024*1024) throw new Error("Выберите непустой файл размером до 256 МБ");
    data.delete("file");
    progressRow.hidden = false;
    progress.value = 0;
    stage.textContent = "Передаём файл";
    percentage.textContent = "0%";
    cancel.disabled = false;
    chooser.disabled = true;
    controller = new AbortController();
    const abortOnLeave = () => controller?.abort();
    window.addEventListener("hashchange",abortOnLeave,{once:true});
    try {
      const result = await uploadRequest("/api/videos?"+new URLSearchParams(data),file,percent => {
        progress.value = percent;
        percentage.textContent = percent < 100 ? percent + "%" : "";
        if (percent === 100) {
          stage.textContent = "Сохраняем видео";
          cancel.disabled = true;
        }
      },controller.signal);
      note("Видео загружено и добавлено в очередь");
      location.hash = watchUrl(result.id);
    } finally {
      window.removeEventListener("hashchange",abortOnLeave);
      controller = undefined;
      progressRow.hidden = true;
      chooser.disabled = false;
    }
  })},
    el("h1",{},"Загрузка видео"),drop,
    field("Название",input("title",{maxlength:140,placeholder:"Как называется ваше видео?"})),
    field("Описание",el("textarea",{name:"description",maxlength:4000,rows:4,placeholder:"Расскажите, о чём ваше видео"})),
    el("div",{class:"form-columns"},
      field("Категория",el("select",{name:"category"},categories.slice(1).map(([key,label]) => el("option",{value:key,selected:key==="Other"},label)))),
      field("Доступ",el("select",{name:"visibility"},el("option",{value:"public"},"Публичное"),el("option",{value:"private"},"Приватное")))),
    progressRow,status,el("div",{},send));
}

function subscribeButton(handle, subscribed, update) {
  if (user?.handle === handle) return null;
  return action(subscribed?"Вы подписаны":"Подписаться",
    mutate(channelApi(handle)+"/subscribe","PUT",{enabled:!subscribed},null,update),subscribed?"":"primary");
}

function commentCard(item) {
  return el("article",{class:"comment"},avatar(item.author),el("div",{},
    el("a",{href:channelUrl(item.author)},"@"+item.author)," ",el("small",{},age(item.created)),el("p",{},item.body)));
}

function shareDialog(id) {
  const url = new URL(watchUrl(id),location.href).href;
  const link = el("input",{value:url,readonly:true,"aria-label":"Ссылка на видео"});
  const copied = feedback();
  const copy = action("Копировать",async () => {
    try {
      await navigator.clipboard.writeText(url);
      copied.textContent = "Ссылка скопирована";
    } catch {
      link.focus();
      link.select();
      copied.textContent = "Скопируйте выделенную ссылку";
    }
  },"primary");
  const dialog = el("dialog",{class:"panel share-dialog","aria-labelledby":"share-title"},
    el("h2",{id:"share-title"},"Поделиться видео"),
    link,copied,el("div",{class:"row"},copy,action("Закрыть",() => dialog.close())));
  const button = action([icon("link"),"Поделиться"],() => {
    copied.textContent = "";
    dialog.showModal();
    link.select();
  });
  return {dialog,button};
}

async function ownerControls(video, base, visibilityLabel) {
  const [grants, channel] = await Promise.all([api(base+"/grants"),api(channelApi(video.owner))]);
  const grantList = el("div",{class:"row spaced"});
  function showGrants(handles) {
    grantList.hidden = handles.length === 0;
    grantList.replaceChildren(...handles.map(handle => action("@"+handle+" · отозвать",
      mutate(base+"/grants/"+encodeURIComponent(handle),"PUT",{enabled:false},"Доступ отозван",
        async () => showGrants(await api(base+"/grants"))))));
  }
  showGrants(grants);
  const visibility = el("div",{class:"row spaced"});
  function showVisibility(value) {
    const next = value === "private" ? "public" : "private";
    visibility.replaceChildren(action(next === "private" ? "Сделать приватным" : "Сделать публичным",
      mutate(base+"/visibility","PATCH",{visibility:next},"Доступ обновлён",result => {
        showVisibility(result.visibility);
        visibilityLabel.hidden = !video.hidden && result.visibility !== "private";
      })));
  }
  showVisibility(video.visibility);
  return el("details",{class:"panel spaced"},el("summary",{},"Управление видео"),
    visibility,
    el("form",{class:"stack spaced",onsubmit:formAction(async form => {
      await api(base+"/grants/"+encodeURIComponent(form.elements.handle.value.trim()),"PUT",{enabled:true});
      showGrants(await api(base+"/grants"));
      form.reset();
      note("Доступ выдан");
    })},field("Имя зрителя для доступа к приватному видео",input("handle",{maxlength:32})),feedback(),
      el("div",{},submit("Выдать доступ"))),
    grantList,
    channel.playlists.length ? el("form",{class:"stack spaced",onsubmit:formAction(async form => {
      await api("/api/playlists/"+form.elements.list.value+"/items/"+video.id,"PUT",{enabled:true});
      note("Добавлено в плейлист");
    })},field("Плейлист",el("select",{name:"list"},channel.playlists.map(item => el("option",{value:item.id},item.title)))),
      feedback(),el("div",{},submit("Добавить в плейлист"))) :
      el("div",{class:"spaced"},pill("Создать плейлист",href("channel",video.owner,{tab:"playlists"}))));
}

function processingPage(video, base, stamp, route) {
  const pending = ["queued","processing"].includes(video.state);
  if (pending) setTimeout(() => {
    if (revision === stamp && location.hash === route) render();
  },2400);
  const message = video.state === "queued" ? "Видео в очереди на обработку." :
    video.state === "processing" ? "Подготавливаем видео для просмотра." :
    "Проверьте, что исходный файл воспроизводится. Если ошибка повторится, загрузите другой файл.";
  return el("section",{class:"sheet panel video-state"},
    el("span",{class:"upload-icon"},icon(pending ? "clock" : "warning")),
    el("h1",{},video.title),
    el("strong",{role:"status"},statusNames[video.state] || video.state),
    el("p",{class:"muted"},message),
    el("div",{class:"row"},
      video.state === "failed" && user?.handle === video.owner ?
        action("Повторить обработку",mutate(base+"/retry","POST",undefined,"Видео снова в очереди"),"primary") : null,
      video.state === "failed" ? pill("Загрузить другой файл",href("upload")) : null,
      pill("Мой канал",channelUrl(video.owner))));
}

async function watchPage(id, params) {
  const mine = revision;
  const route = location.hash;
  const base = endpoint(id);
  const video = await api(base);
  if (video.state !== "ready") return processingPage(video,base,mine,route);
  const visibilityLabel = el("p",{class:"visibility",hidden:!video.hidden && video.visibility !== "private"},
    icon("lock"),statusNames[video.hidden?"hidden":"private"]);
  const isOwner = user?.handle === video.owner;
  const commentQuery = new URLSearchParams({offset:params.get("offset") || "0"});
  const [comments, feed, controls] = await Promise.allSettled([
    api(base+"/comments?"+commentQuery),
    api("/api/videos"),
    isOwner ? ownerControls(video,base,visibilityLabel) : null,
  ]);
  const views = el("strong",{});
  const updateViews = count => {
    views.textContent = numbers.format(count)+" просм. · "+dates.format(date(video.created));
  };
  updateViews(video.views);
  const playbackError = el("div",{class:"notice spaced",hidden:true,role:"status"},
    "Не удалось воспроизвести видео. ",action("Повторить",() => {
      playbackError.hidden = true;
      player.load();
    }));
  let playRecorded = false;
  const player = el("video",{class:"player",src:base+"/media",poster:base+"/poster",controls:true,playsinline:true,preload:"metadata",
    "aria-label":video.title,onerror:() => {playbackError.hidden = false;},
    onplaying:() => {
      if (!playRecorded) {
        playRecorded = true;
        api(base+"/view","POST").then(() => updateViews(video.views+1)).catch(() => {playRecorded = false;});
      }
    }});
  const commentList = el("div",{},comments.status === "fulfilled" ?
    comments.value.map(commentCard) : notice("Комментарии временно недоступны"));
  const commentForm = user ? el("form",{class:"stack",onsubmit:formAction(async form => {
    const item = await api(base+"/comments","POST",{body:form.elements.body.value});
    commentList.prepend(commentCard(item));
    form.reset();
  })},field("Ваш комментарий",el("textarea",{name:"body",required:true,maxlength:2000,rows:2,placeholder:"Добавьте комментарий"})),
  feedback(),el("div",{},submit("Отправить"))) : pill("Войдите, чтобы оставить комментарий",href("login","",{next:"/watch/"+id}),"outline");
  const share = shareDialog(id);
  const theater = action(icon("theater"),() => {
    const on = main.classList.toggle("theater");
    theater.setAttribute("aria-pressed",String(on));
  },"theater-button");
  theater.setAttribute("aria-label","Широкий режим");
  theater.title = "Широкий режим";
  theater.setAttribute("aria-pressed",String(main.classList.contains("theater")));
  const like = action([],async event => {
    if (!guard()) return;
    const button = event.currentTarget;
    button.disabled = true;
    try {
      await api(base+"/like","PUT",{enabled:!video.liked});
      const updated = await api(base);
      video.liked = updated.liked;
      showLike(updated.likes);
    } catch (error) {
      note(error.message);
    } finally {
      button.disabled = false;
    }
  });
  function showLike(count) {
    like.replaceChildren(icon("like"),numbers.format(count));
    like.setAttribute("aria-label",video.liked?"Убрать лайк":"Поставить лайк");
    like.setAttribute("aria-pressed",String(video.liked));
  }
  showLike(video.likes);
  const buttons = el("div",{class:"row"},like,share.button,theater);
  let extras = null;
  if (isOwner) {
    extras = controls.status === "fulfilled" ? controls.value : notice("Управление видео временно недоступно");
  } else if (video.visibility === "public") {
    const reportForm = el("form",{class:"stack",onsubmit:formAction(async form => {
      await api(base+"/reports","POST",{reason:form.elements.reason.value});
      form.reset();
      extras.open = false;
      note("Жалоба отправлена");
    })},field("Причина жалобы",el("textarea",{name:"reason",required:true,maxlength:400,rows:2})),feedback(),
      el("div",{},submit("Отправить жалобу")));
    extras = el("details",{class:"panel spaced"},el("summary",{},"Пожаловаться"),
      el("div",{class:"spaced"},user?reportForm:pill("Войти",href("login","",{next:"/watch/"+id}))));
  }
  const profile = el("div",{class:"profile"},el("a",{href:channelUrl(video.owner),"aria-label":"Канал "+video.owner},avatar(video.owner)),
    el("a",{href:channelUrl(video.owner)},"@"+video.owner));
  function addSubscription(subscribed) {
    const button = subscribeButton(video.owner,subscribed,result => {button.remove(); addSubscription(result.subscribed);});
    if (button) profile.append(button);
  }
  addSubscription(video.subscribed);
  const related = feed.status === "fulfilled" ? feed.value.filter(item => item.id!==id).slice(0,9) : [];
  return el("div",{class:"watch"},el("div",{},player,playbackError,el("h1",{},video.title),
    el("div",{class:"watch-actions"},profile,buttons),
    share.dialog,
    el("div",{class:"description"},views,visibilityLabel,
      video.description && el("p",{},video.description)),extras,
    el("section",{class:"comments"},el("h2",{},"Комментарии"),commentForm,commentList,
      comments.status === "fulfilled" ? pageMore(watchUrl(id),params,comments.value.length,50) : null)),
    related.length ? el("aside",{class:"related","aria-label":"Другие видео"},el("h2",{},"Другие видео"),grid(related)) : null);
}

async function channelPage(handle, params) {
  const offset = params.get("offset") || "0";
  const channel = await api(channelApi(handle)+"?offset="+offset);
  const own = user?.handle === channel.handle;
  const lists = params.get("tab")==="playlists";
  const heading = el("div",{class:"channel-head"},avatar(channel.handle,"large"),el("div",{},
    el("h1",{},channel.handle),el("p",{class:"muted"},"@"+channel.handle+" · "+numbers.format(channel.subscribers)+" подп."),
    own ? pill("Загрузить видео",href("upload"),"primary") : subscribeButton(channel.handle,channel.subscribed,render)));
  const tabs = el("div",{class:"tabs"},pill("Видео",channelUrl(handle),lists?"":"primary"),
    pill("Плейлисты",href("channel",handle,{tab:"playlists"}),lists?"primary":""));
  const create = own && lists ? el("form",{class:"panel stack spaced",onsubmit:formAction(async form => {
    await api("/api/playlists","POST",{title:form.elements.title.value});
    render();
  })},field("Название нового плейлиста",input("title",{maxlength:100})),feedback(),el("div",{},submit("Создать плейлист"))) : null;
  const items = lists ? [
    channel.playlists.length ? el("div",{class:"playlist-grid"},channel.playlists.map(list =>
      el("a",{class:"panel",href:href("playlist",list.id)},icon("play"),el("h3",{},list.title)))) : notice("Плейлистов пока нет"),create
  ] : [grid(channel.videos),pageMore(channelUrl(handle),params,channel.videos.length,24)];
  return [heading,tabs,items];
}

async function playlistPage(id) {
  const list = await api("/api/playlists/"+encodeURIComponent(id));
  const videos = grid(list.videos);
  if (user?.handle === list.owner) {
    videos.querySelectorAll(".card").forEach((item,i) => item.append(el("div",{class:"spaced"},
      action("Убрать из плейлиста",mutate("/api/playlists/"+id+"/items/"+list.videos[i].id,"PUT",{enabled:false},"Видео убрано")))));
  }
  return [el("h1",{},list.title),el("p",{class:"meta"},el("a",{href:channelUrl(list.owner)},"@"+list.owner)),videos];
}

async function moderationPage(params) {
  const rows = await api("/api/moderation/reports?offset="+(params.get("offset") || "0"));
  return [el("h1",{},"Модерация"),rows.length ? rows.map(item => el("article",{class:"panel report"},
    el("h2",{},item.private || item.hidden ? item.title : el("a",{href:watchUrl(item.video)},item.title)),
    el("p",{class:"meta"},"@"+item.reporter+" · "+(statusNames[item.status] || item.status)),
    el("p",{},item.reason),el("div",{class:"row"},
      action(item.hidden?"Восстановить":"Скрыть",mutate("/api/moderation/reports/"+item.id,"PUT",
        {action:item.hidden?"restore":"hide"},"Решение сохранено"),item.hidden?"":"danger"),
      item.status==="open" && action("Отклонить",mutate("/api/moderation/reports/"+item.id,"PUT",{action:"dismiss"},"Жалоба отклонена"))))) :
    notice("Жалоб пока нет"),pageMore(href("moderation"),params,rows.length,50)];
}

function adminPage() {
  if (user?.role !== "admin") return notice("Требуется аккаунт администратора");
  return el("form",{class:"panel sheet stack",onsubmit:formAction(async form => {
    await api("/api/admin/users/"+encodeURIComponent(form.elements.handle.value.trim())+"/role","PUT",{role:form.elements.role.value});
    note("Роль обновлена"); form.reset();
  })},el("h1",{},"Роли пользователей"),field("Имя пользователя",input("handle",{maxlength:32})),
  field("Роль",el("select",{name:"role"},el("option",{value:"user"},"Пользователь"),
    el("option",{value:"moderator"},"Модератор"),el("option",{value:"admin"},"Администратор"))),
  feedback(),el("div",{},submit("Сохранить")));
}

async function render({focus = false} = {}) {
  const stamp = ++revision;
  main.setAttribute("aria-busy","true");
  let result;
  try {
    const [route,search] = location.hash.replace(/^#\/?/,"").split("?",2);
    const [page,rawId] = route.split("/");
    const id = decodeURIComponent(rawId || "");
    const params = new URLSearchParams(search);
    if (page !== "watch") main.classList.remove("theater");
    main.dataset.page = page || "home";
    shell(page,id,params,focus);
    switch (page) {
      case "": case "search": case "subscriptions": result = await feedPage(page,params); break;
      case "watch": result = await watchPage(id,params); break;
      case "channel": result = await channelPage(id,params); break;
      case "playlist": result = await playlistPage(id); break;
      case "login": case "register": result = await authPage(page,params); break;
      case "upload": result = uploadPage(); break;
      case "moderation": result = await moderationPage(params); break;
      case "admin": result = adminPage(); break;
      default: result = notice("Страница не найдена. ",pill("На главную",href("")));
    }
  } catch (error) {
    result = notice(error.message," ",pill("На главную",href("")));
  }
  if (stamp !== revision) return;
  main.replaceChildren(...[result].flat(Infinity).filter(Boolean));
  main.setAttribute("aria-busy","false");
  if (focus) main.focus({preventScroll:true});
}

menu.append(icon("menu"));
document.querySelector("#search-button").append(icon("search"));
function updateMenu() {
  const expanded = mobile.matches ? document.body.classList.contains("mobile-menu") :
    !document.body.classList.contains("collapsed");
  menu.setAttribute("aria-expanded",String(expanded));
  scrim.hidden = !mobile.matches || !expanded;
  main.inert = !scrim.hidden;
}

function closeMenu(restoreFocus = false) {
  document.body.classList.remove("mobile-menu");
  updateMenu();
  if (restoreFocus) menu.focus();
}

menu.addEventListener("click",() => {
  document.body.classList.toggle(mobile.matches ? "mobile-menu" : "collapsed");
  updateMenu();
});
mobile.addEventListener("change",() => closeMenu());
scrim.addEventListener("click",() => closeMenu(true));
nav.addEventListener("click",event => {
  if (mobile.matches && event.target.closest("a, button")) closeMenu(true);
});
updateMenu();
document.querySelector(".skip").addEventListener("click",event => {
  event.preventDefault();
  closeMenu();
  main.focus();
});
document.addEventListener("keydown",event => {
  if (event.key === "Escape" && document.body.classList.contains("mobile-menu")) closeMenu(true);
  if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey ||
      document.querySelector("dialog[open]") ||
      event.target.matches?.("input, textarea, select, [contenteditable]")) return;
  event.preventDefault();
  closeMenu();
  query.focus();
});
document.querySelector("#search").addEventListener("submit",event => {
  event.preventDefault();
  const q = query.value.trim();
  if (q) location.hash = href("search","",{q});
  else goHome();
});
window.addEventListener("hashchange",() => {
  closeMenu();
  window.scrollTo(0,0);
  render({focus:true});
});
try {user = await api("/api/me");} catch (error) {note(error.message);}
render();
