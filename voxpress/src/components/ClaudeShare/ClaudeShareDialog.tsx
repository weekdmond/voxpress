import { useEffect, useMemo, useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import { toast } from 'sonner';
import { api, apiUrl } from '@/lib/api';
import type { ArticleClaudeShare } from '@/types/api';
import { Button, Icon } from '@/components/primitives';
import s from './ClaudeShareDialog.module.css';

interface ClaudeShareDialogProps {
  open: boolean;
  articleIds: string[];
  onClose: () => void;
}

const DEFAULT_DETAIL =
  '请先通读原稿包，保留事实、人物和机构名称，基于这些原稿写一篇结构清晰、适合公众号发布的中文文章。';

function absoluteApiUrl(path: string): string {
  return new URL(apiUrl(path), window.location.href).href;
}

function buildPrompt(share: ArticleClaudeShare, downloadUrl: string, detail: string): string {
  const visibleArticles = share.articles
    .slice(0, 8)
    .map((article, index) => `${index + 1}. ${article.title} / ${article.creator_name}`)
    .join('\n');
  const more =
    share.articles.length > 8 ? `\n...另有 ${share.articles.length - 8} 篇在原稿包中` : '';
  return [
    '请阅读我从 VoxPress 分享的文章原稿包，然后基于这些原稿协助我写文章。',
    '',
    `原稿包文件: ${share.file_name}`,
    `下载链接: ${downloadUrl}`,
    '',
    '如果当前会话已经附上 Markdown 文件，请直接读取附件；如果没有附件，请先通过下载链接获取原稿包。',
    '',
    `文章列表:\n${visibleArticles}${more}`,
    '',
    `写作要求:\n${detail.trim() || DEFAULT_DETAIL}`,
  ].join('\n');
}

async function copyText(text: string): Promise<void> {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const node = document.createElement('textarea');
  node.value = text;
  node.style.position = 'fixed';
  node.style.opacity = '0';
  document.body.appendChild(node);
  node.select();
  document.execCommand('copy');
  document.body.removeChild(node);
}

export function ClaudeShareDialog({ open, articleIds, onClose }: ClaudeShareDialogProps) {
  const [mode, setMode] = useState<'desktop' | 'web'>('desktop');
  const [detail, setDetail] = useState(DEFAULT_DETAIL);
  const idsKey = articleIds.join(',');
  const createShare = useMutation({
    mutationFn: (ids: string[]) =>
      api.post<ArticleClaudeShare>('/api/articles/share/claude', { article_ids: ids }),
    onError: (err: Error) => toast.error(err.message || '生成 Claude 分享包失败'),
  });

  useEffect(() => {
    if (!open) return;
    setMode('desktop');
    if (articleIds.length > 0) createShare.mutate(articleIds);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, idsKey]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  const share = createShare.data;
  const downloadUrl = share ? absoluteApiUrl(share.download_url) : '';
  const prompt = useMemo(
    () => (share ? buildPrompt(share, downloadUrl, detail) : ''),
    [share, downloadUrl, detail],
  );
  const desktopUrl = useMemo(() => {
    if (!share) return '';
    const params = new URLSearchParams({ q: prompt, file: share.local_file_path });
    return `claude://cowork/new?${params.toString()}`;
  }, [share, prompt]);
  const webUrl = useMemo(() => {
    if (!share) return '';
    const params = new URLSearchParams({ q: prompt });
    return `https://claude.ai/new?${params.toString()}`;
  }, [share, prompt]);

  if (!open) return null;

  const pending = createShare.isPending;
  const missingCount = share?.missing_ids.length ?? 0;
  const primaryLabel = mode === 'desktop' ? '打开 Claude 桌面端' : '打开 Claude Web';
  const primaryAction = () => {
    if (!share) return;
    if (mode === 'desktop') {
      window.location.href = desktopUrl;
    } else {
      window.open(webUrl, '_blank', 'noopener,noreferrer');
    }
  };

  return (
    <>
      <div className={s.scrim} onClick={onClose} />
      <div className={s.dialog} role="dialog" aria-modal="true" aria-label="分享给 Claude">
        <div className={s.header}>
          <div className={s.tabs}>
            <button
              className={mode === 'desktop' ? s.tabOn : undefined}
              onClick={() => setMode('desktop')}
            >
              Claude 桌面端
            </button>
            <button className={mode === 'web' ? s.tabOn : undefined} onClick={() => setMode('web')}>
              Claude Web
            </button>
          </div>
          <button className={s.close} onClick={onClose} aria-label="关闭">
            ×
          </button>
        </div>

        <div className={s.body}>
          {pending ? (
            <div className={s.loading}>正在打包文章原稿…</div>
          ) : share ? (
            <>
              <div className={s.summary}>
                <b>{share.article_count}</b> 篇文章已打包为 <span>{share.file_name}</span>
                {missingCount ? <em> · {missingCount} 篇未找到</em> : null}
              </div>

              <div className={s.terminal}>
                <div className={s.terminalTop}>
                  <span />
                  <span />
                  <span />
                  <b>{mode === 'desktop' ? 'Claude Desktop' : 'Claude Web'}</b>
                </div>
                <pre>{prompt}</pre>
              </div>

              <div className={s.actions}>
                <Button
                  variant="primary"
                  onClick={primaryAction}
                  icon={<Icon name="external" size={13} />}
                >
                  {primaryLabel}
                </Button>
                <Button
                  onClick={() =>
                    copyText(prompt)
                      .then(() => toast.success('提示词已复制'))
                      .catch(() => toast.error('复制失败'))
                  }
                  icon={<Icon name="doc" size={13} />}
                >
                  复制提示词
                </Button>
                <a className={s.download} href={downloadUrl} target="_blank" rel="noreferrer">
                  <Icon name="download" size={13} />
                  下载原稿包
                </a>
              </div>

              <label className={s.detailLabel} htmlFor="claude-share-detail">
                补充写作要求
              </label>
              <textarea
                id="claude-share-detail"
                className={s.detail}
                value={detail}
                onChange={(e) => setDetail(e.target.value)}
              />
            </>
          ) : (
            <div className={s.error}>
              <span>分享包生成失败</span>
              <Button size="sm" onClick={() => createShare.mutate(articleIds)}>
                重试
              </Button>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
