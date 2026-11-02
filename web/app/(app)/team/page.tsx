"use client";

/**
 * Who is on the team.
 *
 * Removing someone keeps their calls, because colleagues' coaching plans cite
 * them, so a removal is always undoable and needs only a second click rather
 * than a warning about losing data.
 */

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { PageNote, popToast } from "@/components/Pop";
import { IconArrow } from "@/components/icons";
import { Avatar, ErrorState, LoadingState, SectionHead } from "@/components/ui";
import { ApiError, api } from "@/lib/api";
import { money } from "@/lib/format";
import type { Me, Rep, RepSnapshot, TeamState } from "@/lib/types";

export default function TeamPage() {
  const [team, setTeam] = useState<RepSnapshot[] | null>(null);
  const [archived, setArchived] = useState<Rep[]>([]);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [adding, setAdding] = useState(false);
  const [me, setMe] = useState<Me | null>(null);
  const [access, setAccess] = useState<TeamState | null>(null);
  const [inviteEmail, setInviteEmail] = useState("");
  const [inviteRep, setInviteRep] = useState("");

  const load = useCallback(async () => {
    try {
      const [snapshots, removed, identity] = await Promise.all([
        api.reps(),
        api.archivedReps(),
        api.me(),
      ]);
      setTeam([...snapshots].sort((a, b) => a.rep.name.localeCompare(b.rep.name)));
      setArchived(removed);
      setMe(identity);
      if (identity.user) setAccess(await api.team());
    } catch (e) {
      setError(e as ApiError);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  /** Told apart from the list below: with accounts on, only owners change the team. */
  const canEditTeam = !me?.user || (access?.can_manage ?? false);

  /** Every change goes through here: run it, say what failed, show the truth. */
  async function change(action: () => Promise<unknown>) {
    setNotice(null);
    try {
      await action();
      await load();
      return true;
    } catch (e) {
      setNotice((e as ApiError).detail);
      return false;
    }
  }

  async function add(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setAdding(true);
    if (await change(() => api.addRep(name))) setName("");
    setAdding(false);
  }

  if (error) return <ErrorState message={error.detail} status={error.status} />;
  if (!team) return <LoadingState />;

  return (
    <div className="page" data-status="TEAM" style={{ maxWidth: 940 }}>
      <header className="page-head">
        <div>
          <div className="eyebrow" style={{ marginBottom: 8 }}>
            Team
          </div>
          <h1 className="display d2" style={{ margin: 0 }}>
            Your salespeople
          </h1>
          <PageNote>
            Add people here, or just type a new name when you upload a call and
            they will be added for you.
          </PageNote>
        </div>
      </header>

      {canEditTeam && (
      <form
        onSubmit={add}
        style={{ display: "flex", gap: 10, marginBottom: 18, flexWrap: "wrap" }}
      >
        <input
          className="field"
          aria-label="New salesperson's name"
          placeholder="Salesperson's name"
          value={name}
          maxLength={80}
          onChange={(e) => setName(e.target.value)}
          style={{ flex: "1 1 240px", width: "auto" }}
        />
        <button type="submit" className="btn btn-primary" disabled={!name.trim() || adding}>
          {adding ? "Adding…" : "Add salesperson"}
        </button>
      </form>
      )}

      {notice && (
        <div
          role="alert"
          className="panel"
          style={{
            padding: "12px 15px",
            marginBottom: 16,
            borderColor: "var(--rose)",
            color: "var(--rose)",
            fontSize: 13,
          }}
        >
          {notice}
        </div>
      )}

      <section className="panel panel-flush" style={{ marginBottom: 22 }}>
        <SectionHead
          title="On the team"
          hint={`${team.length} ${team.length === 1 ? "person" : "people"}`}
        />
        {team.length === 0 ? (
          <p style={{ padding: "22px 18px", margin: 0, fontSize: 13.5, color: "var(--ink-3)" }}>
            Nobody yet. Add your first salesperson above, or{" "}
            <Link href="/upload" style={{ color: "var(--willow)" }}>
              upload a call
            </Link>
            .
          </p>
        ) : (
          <div>
            {team.map((snapshot) => (
              <Row
                key={snapshot.rep.id}
                snapshot={snapshot}
                canEdit={canEditTeam}
                onSave={(update) => change(() => api.editRep(snapshot.rep.id, update))}
                onRemove={() => change(() => api.removeRep(snapshot.rep.id))}
              />
            ))}
          </div>
        )}
      </section>

      {me?.user && access && (
        <section className="panel panel-flush" style={{ marginBottom: 22 }}>
          <SectionHead title="Who can sign in" hint={me.user.org_name} />
          {access.members.map((member) => (
            <div key={member.id} className="team-row">
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 13.5, fontWeight: 500 }}>{member.name}</div>
                <div style={{ fontSize: 11.5, color: "var(--ink-3)" }}>
                  {member.email} · {member.role}
                </div>
              </div>
              {access.can_manage && member.id !== me.user?.id && (
                <>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() =>
                      change(() => api.setRole(member.id, member.role === "owner" ? "member" : "owner"))
                    }
                  >
                    {member.role === "owner" ? "Make member" : "Make owner"}
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => change(() => api.removeMember(member.id))}
                  >
                    Remove access
                  </button>
                </>
              )}
            </div>
          ))}
          {access.invites.map((invite) => (
            <div key={invite.id} className="team-row">
              <div style={{ flex: 1, minWidth: 0, fontSize: 13.5, color: "var(--ink-2)" }}>
                {invite.email}
                <span className="chip chip-neutral" style={{ marginLeft: 8 }}>
                  invited
                </span>
              </div>
              {access.can_manage && (
                <>
                  {access.mail_enabled && (
                    <button
                      className="btn btn-ghost btn-sm"
                      onClick={() => change(() => api.resendInvite(invite.id))}
                    >
                      Send again
                    </button>
                  )}
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => change(() => api.cancelInvite(invite.id))}
                  >
                    Cancel
                  </button>
                </>
              )}
            </div>
          ))}
          {access.can_manage && (
            <form
              className="team-row"
              style={{ flexWrap: "wrap" }}
              onSubmit={async (event) => {
                event.preventDefault();
                let sent = true;
                const made = await change(async () => {
                  sent = (await api.invite(inviteEmail, inviteRep)).email_sent;
                });
                if (made && access.mail_enabled && !sent) {
                  setNotice("The invite was saved, but the email could not be sent. Tell them directly, or send it again.");
                }
                if (made) {
                  popToast(`Invited ${inviteEmail}`);
                  setInviteEmail("");
                  setInviteRep("");
                }
              }}
            >
              <input
                className="field"
                type="email"
                required
                aria-label="Colleague's email"
                placeholder="colleague@company.com"
                value={inviteEmail}
                onChange={(e) => setInviteEmail(e.target.value)}
                style={{ flex: "2 1 200px", width: "auto" }}
              />
              <select
                className="field"
                aria-label="Which salesperson they are"
                value={inviteRep}
                onChange={(e) => setInviteRep(e.target.value)}
                style={{ flex: "1 1 150px", width: "auto" }}
              >
                <option value="">Not a salesperson</option>
                {team.map(({ rep }) => (
                  <option key={rep.id} value={rep.id}>
                    {rep.name}
                  </option>
                ))}
              </select>
              <button type="submit" className="btn" disabled={!inviteEmail.trim()}>
                Invite
              </button>
              <p style={{ flexBasis: "100%", margin: 0, fontSize: 12, color: "var(--ink-3)" }}>
                {access.mail_enabled
                  ? "They will get an email asking them to sign in using this address."
                  : "No email is sent, because no mail server is set up. Tell them to sign in with Google using this address, which proves it is theirs."}
              </p>
            </form>
          )}
        </section>
      )}

      {archived.length > 0 && (
        <section className="panel panel-flush">
          <SectionHead title="Removed" hint="Their calls are kept" />
          {archived.map((rep) => (
            <div
              key={rep.id}
              style={{
                display: "flex",
                alignItems: "center",
                gap: 12,
                padding: "11px 17px",
                borderBottom: "1px solid var(--rule)",
              }}
            >
              <Link href={`/reps/${rep.id}`} style={{ flex: 1, fontSize: 13.5, color: "var(--ink-2)" }}>
                {rep.name}
              </Link>
              {canEditTeam && (
                <button
                  className="btn btn-sm"
                  onClick={() => change(() => api.restoreRep(rep.id))}
                >
                  Restore
                </button>
              )}
            </div>
          ))}
        </section>
      )}
    </div>
  );
}

/* ---------------------------------------------------------------------- */

function Row({
  snapshot,
  canEdit,
  onSave,
  onRemove,
}: {
  snapshot: RepSnapshot;
  canEdit: boolean;
  onSave: (update: { name: string; quota: number }) => Promise<boolean>;
  onRemove: () => Promise<boolean>;
}) {
  const { rep } = snapshot;
  const [editing, setEditing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [name, setName] = useState(rep.name);
  const [quota, setQuota] = useState(String(rep.quota));

  async function save(event: React.FormEvent) {
    event.preventDefault();
    const parsed = Number(quota);
    if (await onSave({ name, quota: Number.isFinite(parsed) && parsed >= 0 ? parsed : rep.quota })) {
      setEditing(false);
    }
  }

  const rowStyle: React.CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 12,
    padding: "11px 17px",
    borderBottom: "1px solid var(--rule)",
    flexWrap: "wrap",
  };

  if (editing) {
    return (
      <form onSubmit={save} style={rowStyle}>
        <Avatar name={name || rep.name} />
        <input
          className="field"
          aria-label={`Name for ${rep.name}`}
          value={name}
          maxLength={80}
          autoFocus
          onChange={(e) => setName(e.target.value)}
          style={{ flex: "2 1 180px", width: "auto" }}
        />
        <input
          className="field num"
          aria-label={`Quota for ${rep.name}`}
          type="number"
          min={0}
          step="any"
          value={quota}
          onChange={(e) => setQuota(e.target.value)}
          style={{ flex: "1 1 100px", width: "auto" }}
        />
        <button type="submit" className="btn btn-primary btn-sm" disabled={!name.trim()}>
          Save
        </button>
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={() => {
            setName(rep.name);
            setQuota(String(rep.quota));
            setEditing(false);
          }}
        >
          Cancel
        </button>
      </form>
    );
  }

  return (
    <div style={rowStyle}>
      <Avatar name={rep.name} top={rep.is_top_performer} />
      <div style={{ flex: "1 1 180px", minWidth: 0 }}>
        <Link href={`/reps/${rep.id}`} style={{ fontWeight: 500, fontSize: 13.5 }}>
          {rep.name}
        </Link>
        <div style={{ fontSize: 11.5, color: "var(--ink-3)", marginTop: 1 }}>
          {snapshot.calls} {snapshot.calls === 1 ? "call" : "calls"}
          {rep.quota > 0 && ` · ${money(rep.quota)} quota`}
        </div>
      </div>
      <Link href="/upload" className="btn btn-ghost btn-sm">
        Upload a call
        <IconArrow size={11} />
      </Link>
      {canEdit && (
        <button
          className="btn btn-sm"
          onClick={() => {
            setConfirming(false);
            setEditing(true);
          }}
        >
          Edit
        </button>
      )}
      {!canEdit ? null : confirming ? (
        <>
          <button
            className="btn btn-sm"
            style={{ color: "var(--rose)", borderColor: "var(--rose)" }}
            onClick={onRemove}
          >
            Confirm remove
          </button>
          <button className="btn btn-ghost btn-sm" onClick={() => setConfirming(false)}>
            Keep
          </button>
        </>
      ) : (
        <button className="btn btn-ghost btn-sm" onClick={() => setConfirming(true)}>
          Remove
        </button>
      )}
    </div>
  );
}
