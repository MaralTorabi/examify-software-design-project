# Examify — Function Point Analysis | گزارش تحلیل نقاط کارکرد

**Prepared for the Teaching Assistant | تهیه‌شده برای دستیار آموزشی**

**Basis | مبنا** — Examify Architecture v1.0, sections 2.4, 5 and 6.5, and the sprint prototype scope.

## 1. Scope and counting basis | دامنه و مبنای شمارش

The application boundary contains Examify's API, web client, services and application-managed persistence. Students, instructors, API clients, operators and remote providers are outside that boundary. This is a design-stage application estimate using the course inventory and IFPUG complexity matrices. The inventory includes functions assigned to parallel sprint branches. Table names come from architecture §5, and transaction counts use the intended user interface and API contracts.

مرز برنامه شامل API، رابط وب، سرویس‌ها و داده‌های تحت مدیریت Examify است. دانشجویان، استادان، مصرف‌کنندگان API، اپراتورها و ارائه‌دهندگان راه دور خارج از این مرز هستند. این برآورد در مرحلهٔ طراحی، بر اساس فهرست موردنیاز درس و ماتریس‌های پیچیدگی IFPUG تهیه شده است. فهرست شامل قابلیت‌های واگذارشده به شاخه‌های موازی اسپرینت نیز هست. نام جدول‌ها از بخش ۵ معماری و شمارش تراکنش‌ها از رابط و قراردادهای مورد انتظار گرفته شده است.

**DET** is a distinct user-recognizable data element, **RET** a recognizable record subgroup and **FTR** a distinct logical file referenced or maintained by a transaction. Repeating options, citations and report rows are counted by field type. Internal indexes, leases, generated hashes used only for integrity, and transport details are excluded from the DET estimates. Shared authorization middleware is excluded unless access control is part of the transaction's business purpose.

**DET** مؤلفهٔ دادهٔ متمایز و قابل تشخیص برای کاربر، **RET** زیرگروه قابل تشخیص رکورد و **FTR** فایل منطقی متمایز مورد استفاده یا نگهداری در تراکنش است. گزینه‌ها، استنادها و ردیف‌های تکرارشوندهٔ گزارش بر اساس نوع فیلد شمارش شده‌اند. ایندکس‌ها، مهلت پردازش، هش‌های صرفاً کنترلی و جزئیات انتقال از DET کنار گذاشته شده‌اند. میان‌افزار عمومی مجوزدهی هنگامی در شمارش اثر دارد که کنترل دسترسی بخشی از هدف عملیاتی تراکنش باشد.

## 2. Complexity matrices and weights | ماتریس‌ها و وزن‌های پیچیدگی

L = Low / کم · A = Average / متوسط · H = High / زیاد

| ILF/EIF · RET × DET | 1–19 | 20–50 | 51+ |
| --- | --- | --- | --- |
| 1 RET | L | L | A |
| 2–5 RET | L | A | H |
| 6+ RET | A | H | H |

| EI · FTR × DET | 1–4 | 5–15 | 16+ |
| --- | --- | --- | --- |
| 0–1 FTR | L | L | A |
| 2 FTR | L | A | H |
| 3+ FTR | A | H | H |

| EO/EQ · FTR × DET | 1–5 | 6–19 | 20+ |
| --- | --- | --- | --- |
| 0–1 FTR | L | L | A |
| 2–3 FTR | L | A | H |
| 4+ FTR | A | H | H |

| Function / نوع کارکرد | Low / کم | Average / متوسط | High / زیاد |
| --- | ---: | ---: | ---: |
| Internal Logical File (ILF) / فایل منطقی داخلی | 7 | 10 | 15 |
| External Interface File (EIF) / فایل رابط خارجی | 5 | 7 | 10 |
| External Input (EI) / ورودی خارجی | 3 | 4 | 6 |
| External Output (EO) / خروجی خارجی | 4 | 5 | 7 |
| External Inquiry (EQ) / پرس‌وجوی خارجی | 3 | 4 | 6 |

## 3. Data functions | کارکردهای داده‌ای

For the requested course count, each SQLAlchemy table represents one ILF with one RET. The EIF rows model exchanged data groups. The data elements below are the basis of the DET estimates.

در شمارش درخواستی درس، هر جدول SQLAlchemy یک ILF با یک RET است. ردیف‌های EIF گروه‌های دادهٔ مبادله‌شده را مدل می‌کنند. مؤلفه‌های زیر مبنای برآورد DET هستند.

| ID | Logical group / گروه منطقی | Counted attributes / مؤلفه‌های شمارش‌شده | RET | DET | FP |
| --- | --- | --- | ---: | ---: | ---: |
| ILF01 | `users` / کاربران | ID, email, role, active status, created time / شناسه، ایمیل، نقش، وضعیت فعال، زمان ایجاد | 1 | 5 | 7 |
| ILF02 | `documents` / اسناد | ID, owner, filename, size, status, page count, extracted page count, error code, upload time / شناسه، مالک، نام، اندازه، وضعیت، تعداد صفحات، تعداد صفحات استخراج‌شده، کد خطا، زمان بارگذاری | 1 | 9 | 7 |
| ILF03 | `document_pages` / صفحات سند | Document, page number, text / سند، شمارهٔ صفحه، متن | 1 | 3 | 7 |
| ILF04 | `questions` / سؤال‌ها | ID, document, type, prompt, options, correct index, difficulty, explanation, topic, mode, provider, review status, reviewer, review time, run, creation time / شناسه، سند، نوع، صورت، گزینه‌ها، شاخص پاسخ صحیح، دشواری، توضیح، مبحث، حالت، ارائه‌دهنده، وضعیت بازبینی، بازبین، زمان بازبینی، اجرای تولید، زمان ایجاد | 1 | 16 | 7 |
| ILF05 | `question_sources` / استنادهای سؤال | Question, document, page number, excerpt / سؤال، سند، شمارهٔ صفحه، گزیده | 1 | 4 | 7 |
| ILF06 | `exam_sessions` / نشست‌های آزمون | ID, student, state, mode, target count, difficulty, strategy, completion reason, report, creation, start, completion and grading times / شناسه، دانشجو، وضعیت، حالت، تعداد هدف، دشواری، راهبرد، دلیل پایان، گزارش، زمان‌های ایجاد، شروع، پایان و نمره‌دهی | 1 | 13 | 7 |
| ILF07 | `exam_answers` / پاسخ‌ها و سؤال‌های صادرشده | Session, question, sequence, submission ID, selected index, correctness, difficulty at issue, issue time, answer time / نشست، سؤال، ترتیب، شناسهٔ ارسال، شاخص گزینه، درستی، دشواری هنگام صدور، زمان صدور، زمان پاسخ | 1 | 9 | 7 |
| ILF08 | `exam_session_documents` / اسناد هر نشست | Session, document / نشست، سند | 1 | 2 | 7 |
| ILF09 | `exam_session_questions` / مجموعهٔ ثابت سؤال‌های نشست | Session, eligible question / نشست، سؤال واجد شرایط | 1 | 2 | 7 |
| ILF10 | `generation_runs` / اجراهای تولید سؤال | ID, document, requester, status, requested count, difficulty, language, mode, provider, fallback reason / شناسه، سند، درخواست‌کننده، وضعیت، تعداد درخواستی، دشواری، زبان، حالت، ارائه‌دهنده، دلیل جایگزینی | 1 | 10 | 7 |
| ILF11 | `document_permissions` / مجوزهای سند | Document, grantee, permission / سند، دریافت‌کننده، مجوز | 1 | 3 | 7 |
| EIF01 | PDF/Text extractor / استخراج‌گر PDF و متن | Source name, file/text content, page number, page text / نام منبع، محتوای فایل یا متن، شمارهٔ صفحه، متن صفحه | 1 | 4 | 5 |
| EIF02 | External LLM + Mock AI Adapter / مدل زبانی خارجی و آداپتر شبیه‌ساز | Language, difficulty, count, source page, page text, prompt, options, answer index, explanation, topic, cited page, excerpt / زبان، دشواری، تعداد، صفحهٔ منبع، متن صفحه، صورت سؤال، گزینه‌ها، شاخص پاسخ، توضیح، مبحث، صفحهٔ استناد، گزیده | 1 | 12 | 5 |

## 4. Transaction functions | کارکردهای تراکنشی

The logical files referenced below are identified by their IDs in section 3. DETs describe the user-visible boundary at design time. Health Live/Ready is one inquiry in the course inventory.

شناسه‌های جدول زیر به فایل‌های منطقی بخش ۳ ارجاع می‌دهند. DETها بر اساس تبادل قابل مشاهده در مرز برنامه در مرحلهٔ طراحی برآورد شده‌اند. زنده‌بودن و آمادگی هر دو در یک ردیف پرس‌وجو شمارش شده‌اند.

| ID | Function / کارکرد | DET basis / مبنای DET | DET | FTRs / فایل‌های مرجع | Complexity / پیچیدگی | FP |
| --- | --- | --- | ---: | --- | --- | ---: |
| EI01 | Register / ثبت‌نام | Email, password, role, user ID, active status, creation time / ایمیل، گذرواژه، نقش، شناسه، وضعیت فعال، زمان ایجاد | 6 | 01 | L | 3 |
| EI02 | Login / ورود | Email, password, access token, token type / ایمیل، گذرواژه، توکن، نوع توکن | 4 | 01 | L | 3 |
| EI03 | Upload File / بارگذاری فایل | Filename, binary file, document ID, status, page count, extracted count, warning / نام، فایل، شناسهٔ سند، وضعیت، تعداد صفحات، تعداد استخراج‌شده، هشدار | 7 | 02, 03, EIF01 | H | 6 |
| EI04 | Upload Text / ورود متن | Title, text, document ID, status, page count, extracted count, warning / عنوان، متن، شناسهٔ سند، وضعیت، تعداد صفحات، تعداد استخراج‌شده، هشدار | 7 | 02, 03, EIF01 | H | 6 |
| EI05 | Share Doc / اشتراک سند | Document, grantee, permission, outcome / سند، دریافت‌کننده، مجوز، نتیجه | 4 | 01, 02, 11 | A | 4 |
| EI06 | Generate Questions / تولید سؤال | Document, count, difficulty, language, run ID, status / سند، تعداد، دشواری، زبان، شناسهٔ اجرا، وضعیت | 6 | 02, 03, 04, 05, 10, EIF02 | H | 6 |
| EI07 | Review Question / بازبینی سؤال | Question, decision, reviewer, review time / سؤال، تصمیم، بازبین، زمان بازبینی | 4 | 04 | L | 3 |
| EI08 | Create Exam / ایجاد آزمون | Document, target count, initial difficulty, mode, session ID, state / سند، تعداد هدف، دشواری اولیه، حالت، شناسهٔ نشست، وضعیت | 6 | 02, 06, 08 | H | 6 |
| EI09 | Start Exam / آغاز آزمون | Session, state, start time / نشست، وضعیت، زمان شروع | 3 | 04, 06, 08, 09 | A | 4 |
| EI10 | Submit Answer / ارسال پاسخ | Submission, session, question, selection, correctness, next difficulty, answered count, completion status / شناسهٔ ارسال، نشست، سؤال، گزینه، درستی، دشواری بعدی، تعداد پاسخ‌ها، وضعیت تکمیل | 8 | 06, 07 | A | 4 |
| EI11 | Complete Exam / تکمیل آزمون | Session, state, reason, completion time / نشست، وضعیت، دلیل، زمان تکمیل | 4 | 06, 07 | L | 3 |
| EI12 | Grade Exam / نمره‌دهی آزمون | Session, state, score, correct count, answer count, report reference / نشست، وضعیت، امتیاز، تعداد صحیح، تعداد پاسخ، ارجاع گزارش | 6 | 04, 05, 06, 07 | H | 6 |
| EO01 | Analytical Exam Result Report / گزارش تحلیلی نتایج | Session, score, answered count, correct count, topic, topic accuracy, evidence flag, weak topic, recommendation count, difficulty, cited document, page / نشست، امتیاز، تعداد پاسخ، تعداد صحیح، مبحث، دقت مبحث، وضعیت شواهد، مبحث ضعیف، تعداد پیشنهادی، دشواری، سند استناد، شمارهٔ صفحه | 12 | 04, 05, 06, 07 | H | 7 |
| EO02 | Audit/Fallback Log / گزارش حسابرسی و جایگزینی | Run, document, requester, provider, mode, reason, status / اجرا، سند، درخواست‌کننده، ارائه‌دهنده، حالت، دلیل، وضعیت | 7 | 10 | L | 4 |
| EO03 | OpenAPI 3.1 Spec / مشخصات OpenAPI 3.1 | Version, service metadata, server, paths, component definitions / نسخه، مشخصات سرویس، سرور، مسیرها، تعریف مؤلفه‌ها | 5 | 0 (generated metadata / فرادادهٔ تولیدشده) | L | 4 |
| EQ01 | List Docs / فهرست اسناد | ID, filename, size, status, page count, upload time / شناسه، نام، اندازه، وضعیت، تعداد صفحات، زمان بارگذاری | 6 | 02, 11 | A | 4 |
| EQ02 | Get Doc / دریافت سند | ID, filename, size, status, page count, extracted count, upload time, error code / شناسه، نام، اندازه، وضعیت، تعداد صفحات، تعداد استخراج‌شده، زمان بارگذاری، کد خطا | 8 | 02, 11 | A | 4 |
| EQ03 | List Questions / فهرست سؤال‌ها | Document, question ID, prompt, options, difficulty, topic, review status, cited page / سند، شناسهٔ سؤال، صورت، گزینه‌ها، دشواری، مبحث، وضعیت بازبینی، صفحهٔ استناد | 8 | 04, 05 | A | 4 |
| EQ04 | Get Next Adaptive Question / دریافت سؤال تطبیقی بعدی | Session, question ID, sequence, prompt, options, difficulty / نشست، شناسهٔ سؤال، ترتیب، صورت، گزینه‌ها، دشواری | 6 | 04, 06, 07, 09 | H | 6 |
| EQ05 | Health Live/Ready / زنده‌بودن و آمادگی | Probe status, database status, storage status / وضعیت بررسی، وضعیت پایگاه داده، وضعیت ذخیره‌سازی | 3 | 0 (dependency checks / بررسی وابستگی‌ها) | L | 3 |

Bare numeric FTR IDs refer to ILFs. The report EO counts analytical presentation and derivation as the course deliverable. Its FTRs describe the analytical data sources. The report GET in the architecture retrieves an already computed result.

شناسه‌های عددی FTR به ILFها اشاره می‌کنند. در شمارش درس، محاسبه و ارائهٔ تحلیلی گزارش به‌عنوان EO در نظر گرفته شده و FTRها منابع دادهٔ تحلیل هستند. مسیر GET گزارش در معماری نتیجهٔ از پیش محاسبه‌شده را می‌خواند.

## 5. UFP, VAF and AFP | محاسبهٔ نهایی

| Function / نوع | Low / کم | Average / متوسط | High / زیاد | Count / تعداد | UFP subtotal / جمع وزن‌دار |
| --- | ---: | ---: | ---: | ---: | ---: |
| ILF | 11 | 0 | 0 | 11 | 77 |
| EIF | 2 | 0 | 0 | 2 | 10 |
| EI | 4 | 3 | 5 | 12 | 54 |
| EO | 2 | 0 | 1 | 3 | 15 |
| EQ | 1 | 3 | 1 | 5 | 21 |
| **Total / مجموع** | **20** | **6** | **7** | **33** | **177** |

The legacy IFPUG value adjustment uses 14 General System Characteristics with a Degree of Influence (DI) from 0 to 5. These ratings are design assumptions based on architecture and sprint scope.

تعدیل کلاسیک IFPUG از ۱۴ ویژگی عمومی سیستم با درجهٔ اثرگذاری (DI) از ۰ تا ۵ استفاده می‌کند. امتیازهای زیر برآورد طراحی بر اساس معماری و دامنهٔ اسپرینت هستند.

| # | General System Characteristic / ویژگی عمومی | DI | Basis / دلیل |
| --- | --- | ---: | --- |
| 1 | Data communications / ارتباطات داده | 4 | Browser/API and external HTTPS provider / ارتباط مرورگر، API و ارائه‌دهندهٔ خارجی |
| 2 | Distributed data processing / پردازش توزیع‌شده | 3 | Local services delegate live generation remotely / واگذاری تولید زنده از سرویس محلی به ارائه‌دهندهٔ راه دور |
| 3 | Performance / کارایی | 3 | Upload bounds, provider timeouts, bounded retries / حدود بارگذاری، مهلت ارتباط و تلاش مجدد محدود |
| 4 | Heavily used configuration / محدودیت سخت زیرساخت | 0 | No measured resource saturation requirement / الزام اندازه‌گیری‌شده‌ای برای اشباع منابع تعریف نشده است |
| 5 | Transaction rate / نرخ تراکنش | 1 | Interactive prototype with one-by-one exam operations / عملیات تعاملی و مرحله‌ای آزمون |
| 6 | Online data entry / ورود برخط داده | 4 | Registration, uploads, review and answer submission / ثبت‌نام، بارگذاری، بازبینی و ارسال پاسخ |
| 7 | End-user efficiency / بهره‌وری کاربر نهایی | 3 | Guided document-to-exam-to-report flow / جریان هدایت‌شده از سند تا آزمون و گزارش |
| 8 | Online update / به‌روزرسانی برخط | 4 | Permission, review and concurrency-controlled exam changes / تغییر مجوزها، بازبینی و تغییرات آزمون با کنترل هم‌زمانی |
| 9 | Complex processing / پردازش پیچیده | 4 | Citation grounding, adaptive selection, topic analytics / اعتبارسنجی استناد، انتخاب تطبیقی و تحلیل مبحثی |
| 10 | Reusability / استفادهٔ مجدد | 3 | Provider adapter and strategy interfaces / رابط‌های آداپتر و راهبرد |
| 11 | Installation ease / سهولت نصب | 2 | Python environment, migration design and local databases / محیط پایتون، طرح مهاجرت و پایگاه دادهٔ محلی |
| 12 | Operational ease / سهولت بهره‌برداری | 3 | Health probes, fallback and lease-based recovery / بررسی سلامت، جایگزینی و بازیابی مبتنی بر مهلت پردازش |
| 13 | Multiple sites / استقرار چندسایتی | 0 | No multi-site requirement in prototype scope / استقرار چندسایتی در دامنهٔ نمونهٔ اولیه تعریف نشده است |
| 14 | Facilitate change / تسهیل تغییر | 3 | Configurable provider and replaceable adaptive strategies / ارائه‌دهندهٔ قابل پیکربندی و راهبردهای تطبیقی قابل جایگزینی |
| | **Total Degree of Influence / مجموع درجهٔ اثرگذاری** | **37** | |

- **UFP / نقاط کارکرد تعدیل‌نشده** = 77 + 10 + 54 + 15 + 21 = **177**
- **VAF / ضریب تعدیل ارزش** = 0.65 + (37 ÷ 100) = **1.02**
- **AFP / نقاط کارکرد تعدیل‌شده** = 177 × 1.02 = **180.54**

## 6. IFPUG interpretation | تفسیر طبق قواعد IFPUG

The **177 UFP / 180.54 AFP** result is the requested course count. A standards audit would group user-recognizable data independently of SQL tables, including checking whether child pages, citations and exam pool rows are RETs of parent files. An EIF requires a logical data group maintained by another application and referenced by Examify. The local extraction library, remote adapter and local mock are processing components. The course counts their exchanged data groups separately, and external ownership of persistent groups would need evidence in a standards audit. First-time adaptive issuance writes an answer slot and can progress the session, so a strict classification would assess that elementary process as a state-changing transaction. Retrieving an already persisted report can qualify as an EQ. Technical outputs such as logs, health and OpenAPI should be assessed against the functional requirements recognized by their users. The VAF-adjusted figure is reported for the course using the legacy method, with UFP shown separately.

نتیجهٔ **۱۷۷ نقطهٔ تعدیل‌نشده و ۱۸۰٫۵۴ نقطهٔ تعدیل‌شده** مربوط به شمارش درخواستی درس است. در ممیزی استاندارد، گروه‌های داده بر اساس دید کاربر تعیین می‌شوند و باید بررسی شود که صفحات، استنادها و ردیف‌های مجموعهٔ آزمون RET فایل منطقی والد محسوب می‌شوند یا خیر. EIF باید گروه منطقی‌ای باشد که برنامه‌ای دیگر آن را نگهداری کند و Examify به آن رجوع کند. کتابخانهٔ استخراج، آداپتر راه دور و شبیه‌ساز محلی مؤلفه‌های پردازشی هستند. در شمارش درس گروه‌های دادهٔ مبادله‌شدهٔ آن‌ها لحاظ شده‌اند و برای ممیزی استاندارد باید شواهد نگهداری خارجی ارائه شود. صدور اولیهٔ سؤال تطبیقی جایگاه پاسخ می‌سازد و می‌تواند نشست را پیش ببرد. بنابراین در طبقه‌بندی دقیق‌تر باید به‌عنوان تراکنش تغییردهندهٔ وضعیت بررسی شود. بازیابی گزارش ذخیره‌شده می‌تواند EQ باشد. لاگ، وضعیت سلامت و OpenAPI نیز باید در برابر نیازمندی‌های کارکردی ذی‌نفعان بررسی شوند. رقم تعدیل‌شده برای درس به روش کلاسیک ارائه شده و UFP جداگانه گزارش شده است.

### References | منابع

- [Examify Software Architecture v1.0](../SOFTWARE_ARCHITECTURE.md) and [Sprint task list](../SPRINT_1H_TASKLIST.md).
- [Xia et al., *Information and Software Technology*, vol. 50, pp. 670–683, Tables 1–2](https://www.eng.uwo.ca/electrical/faculty/capretz_l/docs/publications/Wei-IST-v2.pdf).
- [University of Houston–Clear Lake, *Function Points Analysis Training Booklet*, General System Characteristics and Value Adjustment](https://nas.uhcl.edu/boetticher/SWEN5430/FPATrainingBooklet.pdf).
