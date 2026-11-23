"use strict";

const byId = (id) => document.getElementById(id);
const faNumber = new Intl.NumberFormat("fa-IR");
const faPercent = new Intl.NumberFormat("fa-IR", { style: "percent", maximumFractionDigits: 1 });
const levels = { Easy: "آسان", Medium: "متوسط", Hard: "سخت" };
const reviewLabels = { pending: "در انتظار بررسی", approved: "تأیید شده", rejected: "رد شده" };
const errorLabels = {
  AUTHENTICATION_FAILED: "ایمیل، رمز یا نشست ورود معتبر نیست.",
  PERMISSION_DENIED: "دسترسی لازم برای این کار را ندارید.",
  RESOURCE_NOT_FOUND: "مورد درخواستی پیدا نشد.",
  UPLOAD_TOO_LARGE: "حجم فایل یا متن از حد مجاز بیشتر است.",
  UNSUPPORTED_FILE_TYPE: "فایل باید با پسوند PDF یا TXT باشد.",
  INSUFFICIENT_SOURCE_CONTENT: "برای تولید سؤال چند جملهٔ کامل به متن اضافه کنید.",
};

const state = {
  token: "", documents: [], document: null, questions: [], exam: null,
  question: null, submission: null, busy: false,
};

const sampleText = [
  "معماری نرم‌افزار مرزهای میان بخش‌های اصلی یک سامانه را مشخص می‌کند.",
  "معماری لایه‌ای مسئولیت نمایش اطلاعات را از منطق کسب‌وکار جدا می‌کند.",
  "معماری یکپارچهٔ ماژولار چند ماژول را در یک واحد قابل استقرار نگه می‌دارد.",
  "معماری رویدادمحور واکنش اجزای سامانه به رخدادهای منتشرشده را ممکن می‌کند.",
  "الگوی آداپتور به دو جزء با رابط‌های متفاوت اجازه می‌دهد با هم کار کنند.",
  "الگوی راهبرد امکان تغییر الگوریتم را بدون تغییر کد فراخواننده فراهم می‌کند.",
  "الگوی وضعیت رفتار یک شیء را بر اساس وضعیت جاری آن تعیین می‌کند.",
  "الگوی مخزن جزئیات ذخیره‌سازی را پشت رابطی برای دسترسی به داده پنهان می‌کند.",
].join("\n");

function node(tag, text, className) {
  const result = document.createElement(tag);
  if (text !== undefined) result.textContent = text;
  if (className) result.className = className;
  return result;
}

async function request(path, { method = "GET", body } = {}) {
  const headers = {};
  if (state.token) headers.Authorization = `Bearer ${state.token}`;
  let payload = body;
  if (body && !(body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }
  const response = await fetch(path, { method, body: payload, headers, cache: "no-store" });
  const data = await response.json();
  if (!response.ok) {
    const issue = data.error || {};
    const error = new Error(errorLabels[issue.code] || issue.message || "درخواست انجام نشد.");
    error.status = response.status;
    throw error;
  }
  return data;
}

function post(path, body) {
  return request(path, { method: "POST", body });
}

function showPanel(index) {
  const panels = ["auth", "source", "exam", "report"];
  panels.forEach((panel, counter) => {
    byId(`panel-${panel}`).hidden = index !== counter;
    const step = document.querySelectorAll(".steps li")[counter];
    if (index === counter) step.setAttribute("aria-current", "step");
    else step.removeAttribute("aria-current");
  });
  byId(`${panels[index]}-heading`).focus();
}

function showError(message) {
  const alert = byId("alert");
  alert.hidden = !message;
  alert.textContent = message;
}

function logout() {
  Object.assign(state, { token: "", documents: [], document: null, questions: [], exam: null, question: null, submission: null });
  byId("account").hidden = true;
  ["auth-form", "source-form", "upload-form"].forEach((id) => byId(id).reset());
  byId("documents").replaceChildren(new Option("انتخاب منبع", ""));
  byId("question-bank").hidden = true;
  byId("generation-note").textContent = "";
  showError("");
  showPanel(0);
}

async function run(action, control) {
  if (state.busy) return;
  state.busy = true;
  showError("");
  const workspace = document.querySelector(".workspace");
  workspace.setAttribute("aria-busy", "true");
  if (control) control.disabled = true;
  try {
    await action();
  } catch (error) {
    if (error.status === 401 && state.token) logout();
    showError(error instanceof TypeError ? "ارتباط با سرور برقرار نشد. دوباره تلاش کنید." : error.message);
  } finally {
    state.busy = false;
    workspace.removeAttribute("aria-busy");
    if (control?.isConnected) control.disabled = false;
    refreshBankControls();
  }
}

const documentPath = () => `/api/v1/documents/${state.document.document_id}`;
const examPath = () => `/api/v1/exams/${state.exam.session_id}`;

async function loadDocuments(selectedId = "") {
  state.documents = await request("/api/v1/documents");
  byId("documents").replaceChildren(
    new Option("انتخاب منبع", ""),
    ...state.documents.map((item) => new Option(item.title, item.document_id))
  );
  byId("documents").value = selectedId;
  await selectDocument(selectedId);
}

async function selectDocument(docId) {
  state.document = state.documents.find((item) => item.document_id === docId) || null;
  byId("question-bank").hidden = !state.document;
  byId("generation-note").textContent = "";
  if (state.document) await loadQuestions();
}

function refreshBankControls() {
  if (!state.document) return;
  const pending = state.questions.filter((item) => item.review_status === "pending").length;
  const approved = state.questions.filter((item) => item.review_status === "approved" || !state.document.is_owner).length;
  byId("generate").hidden = !state.document.is_owner;
  byId("approve-all").hidden = !state.document.is_owner || !pending;
  byId("start").disabled = !approved;
  byId("bank-summary").textContent = `${faNumber.format(approved)} سؤال قابل استفاده در آزمون`;
}

async function loadQuestions() {
  state.questions = await request(`${documentPath()}/questions`);
  const rows = state.questions.map((question) => {
    const card = node("details", undefined, "question-card");
    const review = question.review_status ? ` · ${reviewLabels[question.review_status]}` : "";
    card.append(node("summary", `${question.prompt} · ${levels[question.difficulty]}${review}`));
    if (state.document.is_owner) {
      const answer = question.options[question.correct_index];
      card.append(node("p", `پاسخ پیشنهادی: ${answer}`, "answer-key"));
      const options = node("ol");
      question.options.forEach((option) => options.append(node("li", option)));
      card.append(options);
      const actions = node("div", undefined, "actions");
      for (const [status, caption] of [["approved", "تأیید"], ["rejected", "رد"]]) {
        if (question.review_status === status) continue;
        const button = node("button", caption, "small secondary");
        button.type = "button";
        button.addEventListener("click", () => run(async () => {
          await reviewQuestion(question.question_id, status);
          await loadQuestions();
        }, button));
        actions.append(button);
      }
      card.append(actions);
    }
    return card;
  });
  byId("questions").replaceChildren(...rows);
  refreshBankControls();
}

function reviewQuestion(questionId, status) {
  return post(`/api/v1/questions/${questionId}/review`, { status });
}

async function finishExam(complete = false) {
  if (complete && state.exam.state === "InProgress") {
    state.exam = await post(`${examPath()}/complete`);
  }
  const report = await post(`${examPath()}/grade`);
  state.exam.state = "Graded";
  renderReport(report);
}

async function loadQuestion() {
  const question = await request(`${examPath()}/next-question`);
  if (!question) {
    state.exam.state = "Completed";
    await finishExam();
    return;
  }
  state.question = question;
  state.submission = null;
  byId("answer-form").hidden = false;
  byId("question-prompt").textContent = question.prompt;
  byId("question-progress").textContent =
    `سؤال ${faNumber.format(question.sequence_number)} از ${faNumber.format(state.exam.target_question_count)}`;
  byId("difficulty").textContent = `سطح سؤال: ${levels[question.difficulty]}`;
  byId("exam-progress").max = state.exam.target_question_count;
  byId("exam-progress").value = question.sequence_number - 1;
  byId("answer-feedback").textContent = "";
  const choices = question.options.map((option, index) => {
    const label = node("label");
    const radio = node("input");
    Object.assign(radio, { name: "answer", type: "radio", value: String(index), required: true });
    label.append(radio, node("span", option));
    return label;
  });
  byId("options").replaceChildren(...choices);
  byId("submit-answer").hidden = false;
  byId("next").hidden = true;
}

function renderList(container, title, lines, empty) {
  container.replaceChildren(node("h3", title));
  if (!lines.length) {
    container.append(node("p", empty, "muted"));
    return;
  }
  const list = node("ul");
  lines.forEach((line) => list.append(node("li", line)));
  container.append(list);
}

function renderReport(report) {
  byId("score").textContent = report.score_ratio === null ? "—" : faPercent.format(report.score_ratio);
  byId("correct").textContent = `${faNumber.format(report.correct_count)} از ${faNumber.format(report.answered_count)}`;
  byId("final-difficulty").textContent = levels[report.final_difficulty];
  byId("report-summary").textContent = `${faNumber.format(report.answered_count)} پاسخ ثبت شد.`;
  const weak = report.recommendations.map((item) => {
    const pages = [...new Set(item.sources.map((source) => faNumber.format(source.page_number)))].join("، ");
    return `${item.topic} · مرور صفحهٔ ${pages} و ${faNumber.format(item.recommended_question_count)} سؤال تمرینی`;
  });
  renderList(byId("weak-topics"), "مباحث نیازمند تمرین", weak, "بر اساس پاسخ‌های ثبت‌شده، موردی به این فهرست اضافه نشد.");
  renderList(
    byId("review-pages"), "صفحه‌های پیشنهادی برای مرور",
    report.review_sources.map((source) => `صفحهٔ ${faNumber.format(source.page_number)} · ${source.topic} — ${source.excerpt}`),
    "صفحه‌ای برای مرور ثبت نشده است."
  );
  showPanel(3);
}

byId("auth-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const control = event.submitter;
  run(async () => {
    const body = { email: byId("email").value.trim(), password: byId("password").value };
    if (control?.id === "register") await post("/api/v1/auth/register", body);
    const result = await post("/api/v1/auth/login", body);
    state.token = result.access_token;
    byId("password").value = "";
    byId("account-email").textContent = body.email;
    byId("account").hidden = false;
    showPanel(1);
    await loadDocuments();
  }, control);
});

byId("logout").addEventListener("click", () => {
  if (!state.busy) logout();
});

byId("sample").addEventListener("click", () => {
  byId("title").value = "طراحی نرم‌افزار";
  byId("source-text").value = sampleText;
  byId("source-text").focus();
});

byId("source-form").addEventListener("submit", (event) => {
  event.preventDefault();
  run(async () => {
    const item = await post("/api/v1/documents/from-text", {
      title: byId("title").value, text: byId("source-text").value,
    });
    await loadDocuments(item.document_id);
  }, event.submitter);
});

byId("upload-form").addEventListener("submit", (event) => {
  event.preventDefault();
  run(async () => {
    const data = new FormData();
    data.append("file", byId("source-file").files[0]);
    const item = await post("/api/v1/documents/upload", data);
    await loadDocuments(item.document_id);
    byId("upload-form").reset();
  }, event.submitter);
});

byId("documents").addEventListener("change", (event) => {
  run(() => selectDocument(event.target.value), event.target);
});

byId("generate").addEventListener("click", (event) => run(async () => {
  byId("generation-note").textContent = "در حال تولید سؤال…";
  let result;
  try {
    result = await post(`${documentPath()}/generate-questions`, { question_count: 8, language: "fa" });
  } finally {
    byId("generation-note").textContent = "";
  }
  byId("generation-note").textContent = result.questions.length
    ? `${faNumber.format(result.questions.length)} سؤال آزمایشی اضافه شد. پاسخ‌ها را پیش از تأیید بررسی کنید.`
    : "از این متن سؤال تازه‌ای به بانک اضافه نشد.";
  await loadQuestions();
}, event.currentTarget));

byId("approve-all").addEventListener("click", (event) => run(async () => {
  try {
    for (const question of state.questions.filter((item) => item.review_status === "pending")) {
      await reviewQuestion(question.question_id, "approved");
    }
  } finally {
    await loadQuestions();
  }
}, event.currentTarget));

byId("start").addEventListener("click", (event) => run(async () => {
  const available = state.questions.filter((item) => item.review_status === "approved" || !state.document.is_owner).length;
  const session = await post("/api/v1/exams", {
    document_id: state.document.document_id,
    target_question_count: Math.min(5, available),
  });
  state.exam = session;
  state.exam = await post(`${examPath()}/start`);
  await loadQuestion();
  showPanel(2);
}, event.currentTarget));

function newSubmissionId() {
  if (crypto.randomUUID) return crypto.randomUUID();
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join("");
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

byId("answer-form").addEventListener("submit", (event) => {
  event.preventDefault();
  run(async () => {
    const selected = byId("options").querySelector("input:checked");
    state.submission ||= {
      submission_id: newSubmissionId(), question_id: state.question.question_id,
      selected_index: Number(selected.value),
    };
    byId("options").querySelectorAll("input").forEach((input) => { input.disabled = true; });
    const receipt = await post(`${examPath()}/submit-answer`, state.submission);
    byId("exam-progress").value = state.question.sequence_number;
    byId("submit-answer").hidden = true;
    byId("answer-feedback").textContent = receipt.is_correct ? "پاسخ درست بود." : "پاسخ نادرست بود.";
    if (receipt.exam_completed) {
      state.exam.state = "Completed";
      await finishExam();
    } else {
      byId("difficulty").textContent = `سطح هدف: ${levels[receipt.next_difficulty]}`;
      byId("next").hidden = false;
      byId("next").focus();
    }
  }, event.submitter);
});

byId("next").addEventListener("click", (event) => run(loadQuestion, event.currentTarget));
byId("finish").addEventListener("click", (event) => run(() => finishExam(true), event.currentTarget));
byId("restart").addEventListener("click", () => showPanel(1));
