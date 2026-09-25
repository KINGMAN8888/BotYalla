/* فريق الحساب: صاحب العمل يدعو موظفيه برابط مخصّص، فيشتغلوا على نفس البوتات
   من حساباتهم هم. الرابط يظهر مرة واحدة بعد إنشائه — القاعدة تحفظ بصمته لا نصّه. */
import { useState } from "react";
import {
  BY, P, t, bi, Icon, Card, Btn, Field, Input, Select, Form,
  Pill, Empty, PageHead, SectionTitle,
} from "../kit.jsx";

const ROLE_LABEL = {
  owner:  () => t("team_role_owner"),
  admin:  () => bi("مدير", "Admin"),
  member: () => bi("موظف", "Member"),
};

function when(ts) {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleDateString(BY.lang === "en" ? "en-GB" : "ar-EG",
    { year: "numeric", month: "short", day: "numeric" });
}

/* رابط يُعرض مرة واحدة — نسخه هو كل الغرض، فالزرّ أهم من النص */
function CopyBox({ value, label }) {
  const [done, setDone] = useState(false);
  return (
    <div className="flex flex-wrap items-center gap-2">
      <code dir="ltr" className="min-w-[240px] flex-1 select-all overflow-x-auto rounded-xl
                                 bg-ink-9/5 px-3 py-2 text-[12.5px] text-ink-1">
        {value}
      </code>
      <Btn sm variant="ghost" icon={done ? "check" : "copy"}
           onClick={() => {
             navigator.clipboard?.writeText(value).then(() => {
               setDone(true); setTimeout(() => setDone(false), 1800);
             });
           }}>
        {done ? t("dev_copied") : (label || t("dev_copy"))}
      </Btn>
    </div>
  );
}

function NewLink({ url }) {
  return (
    <Card spot className="mb-6">
      <SectionTitle icon="link">{t("team_link_made")}</SectionTitle>
      <p className="mt-0 mb-3 text-[13px] text-ink-3">{t("team_copy")}</p>
      <CopyBox value={url} />
    </Card>
  );
}

function InviteForm() {
  return (
    <Card className="mb-6">
      <SectionTitle icon="users">{t("team_invite_new")}</SectionTitle>
      <p className="mt-0 mb-4 text-[13px] leading-relaxed text-ink-3">{t("team_intro")}</p>
      <Form action={P.createUrl}>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[200px] flex-1">
            <Field label={bi("الصلاحية", "Permission")}>
              <Select name="role" defaultValue="member">
                <option value="member">{t("team_role_member")}</option>
                <option value="admin">{t("team_role_admin")}</option>
              </Select>
            </Field>
          </div>
          <div className="min-w-[180px] flex-1">
            <Field label={bi("ملاحظة (اختياري)", "Note (optional)")}>
              <Input name="note" autoComplete="off"
                     placeholder={bi("مثلاً: محمد — خدمة العملاء", "e.g. Mohamed — support")} />
            </Field>
          </div>
          <Btn icon="plus" type="submit">{bi("اعمل رابط", "Create link")}</Btn>
        </div>
      </Form>
    </Card>
  );
}

function Members({ members, role, me }) {
  if (!members.length) {
    return (
      <Card className="mb-6">
        <SectionTitle icon="users">{t("team_members")}</SectionTitle>
        <Empty icon="users" title={t("team_empty")} text={t("team_intro")} />
      </Card>
    );
  }
  return (
    <Card className="mb-6">
      <SectionTitle icon="users">{t("team_members")} · {members.length}</SectionTitle>
      <div className="mt-2 divide-y divide-ink-9/10">
        {members.map((m) => (
          <div key={m.id} className="flex flex-wrap items-center gap-3 py-3">
            <div className="min-w-[160px] flex-1">
              <div className="text-[14px] font-semibold text-ink-1">{m.username}</div>
              {m.email && <div dir="ltr" className="text-[12px] text-ink-3">{m.email}</div>}
            </div>
            <Pill tone={m.team_role === "admin" ? "on" : "mute"}>
              {(ROLE_LABEL[m.team_role] || ROLE_LABEL.member)()}
            </Pill>
            {role === "owner" && m.id !== me && (
              <div className="flex items-center gap-2">
                <Form action={`${P.teamBase}/${m.id}/role`} className="flex items-center gap-2">
                  <Select name="role" defaultValue={m.team_role || "member"} className="!w-auto">
                    <option value="member">{bi("موظف", "Member")}</option>
                    <option value="admin">{bi("مدير", "Admin")}</option>
                  </Select>
                  <Btn sm variant="ghost" icon="check" type="submit">{t("dev_save")}</Btn>
                </Form>
                <Form action={`${P.teamBase}/${m.id}/remove`}
                      confirm={bi(`تخرج ${m.username} من الحساب؟`,
                                  `Remove ${m.username} from the account?`)}>
                  <Btn sm variant="red" icon="trash" type="submit">
                    {bi("إخراج", "Remove")}
                  </Btn>
                </Form>
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

function Invites({ invites }) {
  const open = invites.filter((i) => !i.used_at && !i.revoked_at);
  if (!open.length) return null;
  return (
    <Card>
      <SectionTitle icon="clock">{t("team_invites")} · {open.length}</SectionTitle>
      <div className="mt-2 divide-y divide-ink-9/10">
        {open.map((i) => (
          <div key={i.id} className="flex flex-wrap items-center gap-3 py-3">
            <div className="min-w-[160px] flex-1">
              <div className="text-[13.5px] text-ink-1">{i.note || bi("دعوة", "Invitation")}</div>
              <div className="text-[12px] text-ink-3">
                {bi("تنتهي", "Expires")} {when(i.expires_at)}
              </div>
            </div>
            <Pill tone="mute">{(ROLE_LABEL[i.role] || ROLE_LABEL.member)()}</Pill>
            <Form action={`${P.teamBase}/invite/${i.id}/revoke`}>
              <Btn sm variant="ghost" icon="close" type="submit">{bi("إلغاء", "Cancel")}</Btn>
            </Form>
          </div>
        ))}
      </div>
    </Card>
  );
}

export default function Team() {
  const { members = [], invites = [], newLink, role, me } = P;
  return (
    <>
      <PageHead icon="users" title={t("team_title")} sub={t("team_intro")} />
      {newLink && <NewLink url={newLink} />}
      <InviteForm />
      <Members members={members} role={role} me={me} />
      <Invites invites={invites} />
    </>
  );
}
