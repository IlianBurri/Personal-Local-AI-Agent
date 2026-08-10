import { useEffect, useRef, useState } from 'react';

export default function Sidebar({
  chats,
  activeId,
  dark,
  appName = 'Arca',
  onNew,
  onSelect,
  onRename,
  onDelete,
  onToggleTheme,
  onOpenSettings,
}) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <span className="logo-dot" />
        {appName}
      </div>

      <button className="btn-new" onClick={onNew}>
        <span style={{ marginRight: 6 }}>+</span> New chat
      </button>

      <div className="sidebar-scroll">
        {bucketize(chats).map(([label, items]) => (
          <div key={label} className="bucket">
            <div className="bucket-label">{label}</div>
            {items.map((c) => (
              <ChatRow
                key={c.id}
                chat={c}
                active={c.id === activeId}
                onSelect={onSelect}
                onRename={onRename}
                onDelete={onDelete}
              />
            ))}
          </div>
        ))}
        {chats.length === 0 && <div className="bucket-empty">No chats yet</div>}
      </div>

      <div className="sidebar-footer">
        <button className="footer-btn" onClick={onToggleTheme}>
          {dark ? '\u2600 Light' : '\u263E Dark'}
        </button>
        <button className="footer-btn" onClick={onOpenSettings}>
          \u2699 Settings
        </button>
      </div>
    </aside>
  );
}

function ChatRow({ chat, active, onSelect, onRename, onDelete }) {
  const [renaming, setRenaming] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const inputRef = useRef(null);

  useEffect(() => {
    if (renaming) inputRef.current?.focus();
  }, [renaming]);

  const commitRename = () => {
    const value = inputRef.current?.value ?? '';
    setRenaming(false);
    if (value.trim() && value.trim() !== chat.title) {
      onRename(chat.id, value.trim());
    }
  };

  return (
    <div
      className={`chat-row ${active ? 'active' : ''}`}
      onClick={() => onSelect(chat.id)}
      onContextMenu={(e) => {
        e.preventDefault();
        setMenuOpen(true);
      }}
    >
      {renaming ? (
        <input
          ref={inputRef}
          className="chat-row-input"
          defaultValue={chat.title}
          onBlur={commitRename}
          onKeyDown={(e) => {
            if (e.key === 'Enter') commitRename();
            if (e.key === 'Escape') setRenaming(false);
          }}
          onClick={(e) => e.stopPropagation()}
        />
      ) : (
        <>
          <span className="chat-row-title">{chat.title}</span>
          <button
            className="chat-row-more"
            title="More"
            onClick={(e) => {
              e.stopPropagation();
              setMenuOpen((v) => !v);
            }}
          >
            ⋯
          </button>
          {menuOpen && (
            <RowMenu
              onClose={() => setMenuOpen(false)}
              onRename={() => {
                setMenuOpen(false);
                setRenaming(true);
              }}
              onDelete={() => {
                setMenuOpen(false);
                onDelete(chat.id);
              }}
            />
          )}
        </>
      )}
    </div>
  );
}

function RowMenu({ onClose, onRename, onDelete }) {
  const ref = useRef(null);
  useEffect(() => {
    const close = (e) => {
      if (!ref.current?.contains(e.target)) onClose();
    };
    document.addEventListener('mousedown', close);
    return () => document.removeEventListener('mousedown', close);
  }, [onClose]);

  return (
    <div className="row-menu" ref={ref} onClick={(e) => e.stopPropagation()}>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onRename();
        }}
      >
        Rename
      </button>
      <button
        className="danger"
        onClick={(e) => {
          e.stopPropagation();
          onDelete();
        }}
      >
        Delete
      </button>
    </div>
  );
}

function bucketize(chats) {
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const DAY = 86400000;
  const buckets = { Today: [], Yesterday: [], 'Previous 7 days': [], Older: [] };

  for (const c of chats) {
    const d = c.created_at ? new Date(c.created_at.replace(' ', 'T')) : null;
    if (!d || Number.isNaN(d.getTime())) {
      buckets.Older.push(c);
      continue;
    }
    const dayStart = new Date(d.getFullYear(), d.getMonth(), d.getDate());
    const diff = Math.round((startToday - dayStart) / DAY);
    if (diff <= 0) buckets.Today.push(c);
    else if (diff === 1) buckets.Yesterday.push(c);
    else if (diff <= 7) buckets['Previous 7 days'].push(c);
    else buckets.Older.push(c);
  }
  return Object.entries(buckets).filter(([, items]) => items.length > 0);
}
