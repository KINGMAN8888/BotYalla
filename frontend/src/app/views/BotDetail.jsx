import { useState } from "react";
import {
  BY, P, t, bi, Icon, Card, Btn, Field, Input, Textarea, Form, Grid, Stat,
  Pill, Empty, PageHead, SectionTitle, Table, Tr, Td, num,
} from "../kit.jsx";

/* ------------------------------------------------------ ضبط بالذكاء الاصطناعي */
function AiPanel({ bot, plan }) {
  const [desc, setDesc] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");

  async function run() {
    if (!desc.trim()) { setMsg(bi("اكتب وصف نشاطك أولاً.", "Describe your business first.")); return; }
    setBusy(true); setMsg("");
    try {
      const r = await fetch(`/bot/${bot.id}/ai-setup`, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": BY.csrf },
        body: JSON.stringify({ description: desc }),
      });
      const d = await r.json();
      if (d.ok) { setMsg(bi("تم الضبط ✅ جاري التحديث…", "Configured ✅ refreshing…")); location.reload(); }
      else setMsg(d.error || bi("تعذّر التوليد.", "Generation failed."));
    } catch { setMsg(bi("تعذّر الاتصال.", "Connection failed.")); }
    setBusy(false);
  }

  return (
    <Card className="mb-6 bg-[linear-gradient(120deg,rgb(124_108_246/0.14),transparent)]">
      <SectionTitle icon="sparkles"
        extra={!plan.ai && (
          <a href={BY.urls.pricing} className="no-underline"><Pill tone="off">
            <Icon name="lock" size={12} />{t("ai_basic_badge")}
          </Pill></a>
        )}>
        {t("ai_setup_title")}
      </SectionTitle>
      <p className="mt-0 mb-4 text-[13px] leading-relaxed text-ink-3">{t("ai_setup_desc")}</p>
      <Textarea value={desc} onChange={(e) => setDesc(e.target.value)} placeholder={t("ai_placeholder")} />
      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Btn icon="sparkles" onClick={run} disabled={busy} type="button">
          {busy ? bi("جاري الضبط…", "Working…") : t("ai_run")}
        </Btn>
        {BY.user.role === "admin" && (
          <Btn variant="ghost" sm icon="key" href="/settings">{t("ai_key_btn")}</Btn>
        )}
        {msg && <span className="text-[12.5px] font-bold text-ink-3">{msg}</span>}
      </div>
    </Card>
  );
}

/* ------------------------------------------------------------- ربط الأدمن */
function LinkOwner({ bot }) {
  const cfg = bot.config || {};
  const [link, setLink] = useState(null);
  const [busy, setBusy] = useState(false);

  async function gen() {
    setBusy(true);
    try {
      const r = await fetch(`/bot/${bot.id}/gen-owner-link`, {
        method: "POST", headers: { "X-CSRF-Token": BY.csrf },
      });
      const d = await r.json();
      if (d.ok) setLink(d.link);
    } catch { /* تجاهل */ }
    setBusy(false);
  }

  if (cfg.owner_chat_id)
    return <Pill tone="on"><Icon name="crown" size={13} />{t("admin_linked")}: {cfg.owner_chat_id}</Pill>;

  return (
    <div>
      <p className="mt-0 mb-3 text-[12.5px] leading-relaxed text-ink-3">{t("link_admin_desc")}</p>
      {link ? (
        <Btn variant="green" sm icon="play" href={link} target="_blank" rel="noopener">
          {t("open_tg_start")}
        </Btn>
      ) : (
        <Btn sm icon="link" onClick={gen} disabled={busy} type="button">{t("link_admin_btn")}</Btn>
      )}
    </div>
  );
}

/* -------------------------------------------------------- محرّرات المحتوى */
function ProductsEditor({ products }) {
  const [rows, setRows] = useState(products.length ? products : [{ name: "", price: "", image: "" }]);
  const set = (i, k, v) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <>
      <SectionTitle icon="store">{t("products")}</SectionTitle>
      <div className="flex flex-col gap-3">
        {rows.map((r, i) => (
          <div key={i} className="grid gap-3 sm:grid-cols-[1fr_120px_1fr]">
            <Input name="p_name"  value={r.name}  onChange={(e) => set(i, "name", e.target.value)}  placeholder={t("product")} />
            <Input name="p_price" value={r.price} onChange={(e) => set(i, "price", e.target.value)} placeholder={t("price_egp")} inputMode="decimal" />
            <Input name="p_image" value={r.image || ""} onChange={(e) => set(i, "image", e.target.value)} placeholder={t("image_url_opt")} />
          </div>
        ))}
      </div>
      <div className="mt-3">
        <Btn variant="ghost" sm icon="plus" type="button"
             onClick={() => setRows([...rows, { name: "", price: "", image: "" }])}>
          {t("new_product")}
        </Btn>
      </div>
    </>
  );
}

function MenuEditor({ items }) {
  const [rows, setRows] = useState(items.length ? items : [{ q: "", a: "" }]);
  const set = (i, k, v) => setRows(rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  return (
    <>
      <SectionTitle icon="grid">{t("menu_items_t")}</SectionTitle>
      <div className="flex flex-col gap-3">
        {rows.map((r, i) => (
          <div key={i} className="grid gap-3 sm:grid-cols-2">
            <Input name="m_q" value={r.q} onChange={(e) => set(i, "q", e.target.value)} placeholder={t("menu_q")} />
            <Input name="m_a" value={r.a} onChange={(e) => set(i, "a", e.target.value)} placeholder={t("menu_a")} />
          </div>
        ))}
      </div>
      <div className="mt-3">
        <Btn variant="ghost" sm icon="plus" type="button" onClick={() => setRows([...rows, { q: "", a: "" }])}>
          {t("new_item")}
        </Btn>
      </div>
    </>
  );
}

function BookingEditor({ cfg }) {
  const days = [
    bi("الإثنين", "Mon"), bi("الثلاثاء", "Tue"), bi("الأربعاء", "Wed"),
    bi("الخميس", "Thu"), bi("الجمعة", "Fri"), bi("السبت", "Sat"), bi("الأحد", "Sun"),
  ];
  const active = cfg.working_days;
  return (
    <>
      <SectionTitle icon="calendar">{t("booking_settings")}</SectionTitle>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <Field label={t("service_name")}><Input name="service_name" defaultValue={cfg.service_name || ""} /></Field>
        <Field label={t("days_ahead")}><Input name="days_ahead" type="number" defaultValue={cfg.days_ahead ?? 7} /></Field>
        <Field label={t("slot_minutes")}><Input name="slot_minutes" type="number" defaultValue={cfg.slot_minutes ?? 60} /></Field>
        <Field label={t("open_hour")}><Input name="open_hour" type="number" min="0" max="23" defaultValue={cfg.open_hour ?? 10} /></Field>
        <Field label={t("close_hour")}><Input name="close_hour" type="number" min="0" max="23" defaultValue={cfg.close_hour ?? 22} /></Field>
      </div>
      <div className="mt-4">
        <span className="mb-2 block text-[13px] font-bold text-ink-2">{t("working_days")}</span>
        <div className="flex flex-wrap gap-2">
          {days.map((d, i) => (
            <label key={i} className="cursor-pointer">
              <input type="checkbox" name="working_days" value={i} className="peer sr-only"
                     defaultChecked={active ? active.includes(i) : true} />
              <span className="inline-flex rounded-xl px-3.5 py-2 text-[13px] font-bold text-ink-3
                               shadow-[inset_0_0_0_1px_rgb(255_255_255/0.1)] transition-colors
                               peer-checked:bg-au-violet/25 peer-checked:text-white
                               peer-checked:shadow-[inset_0_0_0_1px_rgb(124_108_246/0.6)]">{d}</span>
            </label>
          ))}
        </div>
      </div>
    </>
  );
}

/* --------------------------------------------------------------- الصفحة */
export default function BotDetail() {
  const { bot, plan = {}, leads = [], orders = [], bookings = [] } = P;
  const cfg = bot.config || {};
  const meta = BY.templates.find((x) => x.k === bot.template) || { icon: "bot", label: bot.template };
  const isFlow = ["flow", "customer_service", "feedback", "support"].includes(bot.template);

  return (
    <>
      <PageHead
        icon={meta.icon}
        title={bot.name}
        sub={meta.label}
        actions={
          <>
            {bot.running ? (
              <Form action={`/bot/${bot.id}/stop`} className="inline">
                <Btn variant="ghost" sm icon="stop" type="submit">{t("stop")}</Btn>
              </Form>
            ) : (
              <Form action={`/bot/${bot.id}/start`} className="inline">
                <Btn variant="green" sm icon="play" type="submit">{t("start")}</Btn>
              </Form>
            )}
            <Btn variant="ghost" sm icon="chart" href={`/bot/${bot.id}/analytics`}>{t("analytics")}</Btn>
            {plan.broadcast
              ? <Btn variant="ghost" sm icon="megaphone" href={`/bot/${bot.id}/broadcast`}>{t("campaign")}</Btn>
              : <Btn variant="ghost" sm icon="lock" href={BY.urls.pricing} title={t("upgrade_req")}>{t("campaign")}</Btn>}
            {isFlow && <Btn variant="ghost" sm icon="flow" href={`/bot/${bot.id}/flow`}>{t("flow_builder")}</Btn>}
            <Form action={`/bot/${bot.id}/delete`} className="inline"
                  confirm={bi("حذف البوت نهائياً؟", "Delete this bot permanently?")}>
              <Btn variant="red" sm icon="trash" type="submit"
                   aria-label={bi("حذف البوت", "Delete bot")} />
            </Form>
          </>
        }
      />

      <div className="mb-6 flex items-center gap-2">
        {bot.running ? <Pill tone="on" dot>{t("running")}</Pill> : <Pill tone="off">{t("stopped")}</Pill>}
        {cfg.bot_username && <Pill tone="mute"><Icon name="bot" size={12} />@{cfg.bot_username}</Pill>}
      </div>

      <Grid cols={4} className="mb-7">
        <Stat icon="users"  value={bot.stats.subscribers} label={t("stat_subs")} />
        <Stat icon="inbox"  value={bot.stats.leads}       label={t("stat_leads")} />
        <Stat icon="store"  value={bot.stats.orders}      label={t("stat_orders")} />
        <Stat icon="wallet" value={bot.stats.revenue}     label={t("stat_revenue")} />
      </Grid>

      <AiPanel bot={bot} plan={plan} />

      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <Card>
          <SectionTitle icon="bolt">{t("quick_setup")}</SectionTitle>
          <LinkOwner bot={bot} />
          <p className="mt-4 mb-0 text-[12.5px] leading-relaxed text-ink-3">{t("id_hint")}</p>
        </Card>
        <Card>
          <SectionTitle icon="link"
            extra={cfg.tg_synced_at ? <Pill tone="on">{t("tg_synced")}</Pill> : <Pill tone="mute">{t("tg_not_synced")}</Pill>}>
            {t("tg_official")}
          </SectionTitle>
          <p className="mt-0 mb-4 text-[12.5px] leading-relaxed text-ink-3">{t("tg_sync_desc")}</p>
          <Form action={`/bot/${bot.id}/sync-telegram`}>
            <Btn variant="ghost" sm icon="link" type="submit">{t("tg_sync_btn")}</Btn>
          </Form>
        </Card>
      </div>

      {/* الإعدادات */}
      <Card className="mb-6">
        <SectionTitle icon="settings">{t("settings_title")}</SectionTitle>
        <Form action={`/bot/${bot.id}/config`}>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label={t("biz_name")}><Input name="business_name" defaultValue={cfg.business_name || ""} /></Field>
            <Field label={t("owner_id_lbl")} hint={t("owner_id_tip")}>
              <Input name="owner_chat_id" defaultValue={cfg.owner_chat_id || ""} placeholder="123456789" />
            </Field>
          </div>
          <div className="mt-4 grid gap-4 sm:grid-cols-2">
            <Field label={t("welcome_msg")}><Textarea name="welcome" defaultValue={cfg.welcome || ""} /></Field>
            <Field label={t("thanks_msg")}><Textarea name="thanks" defaultValue={cfg.thanks || ""} /></Field>
          </div>
          <div className="mt-4">
            <Field label={t("welcome_img")}>
              <Input name="welcome_image" defaultValue={cfg.welcome_image || ""} placeholder="https://..." />
            </Field>
          </div>

          {bot.template === "store" && (
            <div className="mt-7 pt-6 shadow-[inset_0_1px_0_rgb(255_255_255/0.07)]">
              <ProductsEditor products={cfg.products || []} />
            </div>
          )}
          {bot.template === "faq" && (
            <div className="mt-7 pt-6 shadow-[inset_0_1px_0_rgb(255_255_255/0.07)]">
              <MenuEditor items={cfg.menu_items || []} />
            </div>
          )}
          {bot.template === "booking" && (
            <div className="mt-7 pt-6 shadow-[inset_0_1px_0_rgb(255_255_255/0.07)]">
              <BookingEditor cfg={cfg} />
            </div>
          )}

          <div className="mt-6"><Btn icon="check" type="submit">{t("save_settings")}</Btn></div>
        </Form>
      </Card>

      {/* البيانات المُجمّعة */}
      {bot.template === "store" && (
        <DataCard icon="store" title={t("orders_h")} empty={t("no_orders")} rows={orders}
                  exportUrl={`/bot/${bot.id}/export/orders`}
                  head={[t("col_customer"), t("col_phone"), t("col_address"), t("col_total"), t("col_date")]}
                  render={(o) => [o.customer, o.phone, o.address, `${num(o.total)} ${t("egp")}`, o.created_at]} />
      )}
      {bot.template === "booking" && (
        <DataCard icon="calendar" title={t("bookings_h")} empty={t("no_bookings")} rows={bookings}
                  exportUrl={`/bot/${bot.id}/export/bookings`}
                  head={[t("col_customer"), t("col_phone"), t("col_slot"), t("col_status")]}
                  render={(b) => [b.customer, b.phone, b.slot, <Pill tone="on">{b.status}</Pill>]} />
      )}
      {isFlow && (
        <DataCard icon="inbox" title={t("customers")} empty={t("no_customers")} rows={leads}
                  exportUrl={`/bot/${bot.id}/export/leads`}
                  head={[t("field_name"), t("col_date")]}
                  render={(l) => [
                    <div className="flex flex-wrap gap-2">
                      {Object.entries(l.data || {}).map(([k, v]) => (
                        <span key={k} className="rounded-lg bg-white/5 px-2.5 py-1 text-[12px]">
                          <b className="text-ink-3">{k}:</b> {String(v)}
                        </span>
                      ))}
                    </div>, l.created_at]} />
      )}
    </>
  );
}

function DataCard({ icon, title, rows, head, render, empty, exportUrl }) {
  return (
    <Card className="mb-6">
      <SectionTitle icon={icon}
        extra={rows.length > 0 && (
          <Btn variant="ghost" sm icon="download" href={exportUrl}>CSV</Btn>
        )}>
        {title}
      </SectionTitle>
      {rows.length ? (
        <Table head={head}>
          {rows.map((r, i) => (
            <Tr key={i}>{render(r).map((c, j) => <Td key={j}>{c}</Td>)}</Tr>
          ))}
        </Table>
      ) : <Empty icon={icon} title={empty} />}
    </Card>
  );
}
