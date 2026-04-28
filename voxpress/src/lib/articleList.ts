export type ArticleTimeFilter = 'all' | '7d' | '30d' | '90d';
export type ArticleSort =
  | 'published_at:desc'
  | 'updated_at:desc'
  | 'word_count:desc'
  | 'likes_snapshot:desc';

export interface ArticleListState {
  creatorFilter: string;
  time: ArticleTimeFilter;
  tagFilter: string;
  topicFilter: string;
  sort: ArticleSort;
  q: string;
  page: number;
}

export const ARTICLE_PAGE_SIZE = 20;

export const ARTICLE_TIME_OPTIONS: { v: ArticleTimeFilter; label: string }[] = [
  { v: 'all', label: '全部' },
  { v: '7d', label: '近 7 天' },
  { v: '30d', label: '近 30 天' },
  { v: '90d', label: '近 90 天' },
];

export const ARTICLE_SORT_OPTIONS: { v: ArticleSort; label: string }[] = [
  { v: 'published_at:desc', label: '发布时间' },
  { v: 'updated_at:desc', label: '更新时间' },
  { v: 'word_count:desc', label: '字数' },
  { v: 'likes_snapshot:desc', label: '点赞' },
];

const TIME_SET = new Set<ArticleTimeFilter>(ARTICLE_TIME_OPTIONS.map((o) => o.v));
const SORT_SET = new Set<ArticleSort>(ARTICLE_SORT_OPTIONS.map((o) => o.v));

export const DEFAULT_ARTICLE_LIST_STATE: ArticleListState = {
  creatorFilter: 'all',
  time: 'all',
  tagFilter: 'all',
  topicFilter: 'all',
  sort: 'published_at:desc',
  q: '',
  page: 1,
};

function toParams(input: URLSearchParams | string): URLSearchParams {
  return typeof input === 'string' ? new URLSearchParams(input) : input;
}

export function parseArticleListState(input: URLSearchParams | string): ArticleListState {
  const params = toParams(input);
  const rawTime = params.get('since') as ArticleTimeFilter | null;
  const rawSort = params.get('sort') as ArticleSort | null;
  const rawPage = Number.parseInt(params.get('page') ?? '1', 10);
  return {
    creatorFilter: params.get('creator_id') || DEFAULT_ARTICLE_LIST_STATE.creatorFilter,
    time: rawTime && TIME_SET.has(rawTime) ? rawTime : DEFAULT_ARTICLE_LIST_STATE.time,
    tagFilter: params.get('tag') || DEFAULT_ARTICLE_LIST_STATE.tagFilter,
    topicFilter: params.get('topic') || DEFAULT_ARTICLE_LIST_STATE.topicFilter,
    sort: rawSort && SORT_SET.has(rawSort) ? rawSort : DEFAULT_ARTICLE_LIST_STATE.sort,
    q: (params.get('q') || '').trim(),
    page: Number.isFinite(rawPage) && rawPage > 0 ? rawPage : DEFAULT_ARTICLE_LIST_STATE.page,
  };
}

export function buildArticleListSearchParams(state: ArticleListState): URLSearchParams {
  const params = new URLSearchParams();
  if (state.creatorFilter !== DEFAULT_ARTICLE_LIST_STATE.creatorFilter) {
    params.set('creator_id', state.creatorFilter);
  }
  if (state.tagFilter !== DEFAULT_ARTICLE_LIST_STATE.tagFilter) {
    params.set('tag', state.tagFilter);
  }
  if (state.topicFilter !== DEFAULT_ARTICLE_LIST_STATE.topicFilter) {
    params.set('topic', state.topicFilter);
  }
  if (state.time !== DEFAULT_ARTICLE_LIST_STATE.time) {
    params.set('since', state.time);
  }
  if (state.q) {
    params.set('q', state.q);
  }
  if (state.sort !== DEFAULT_ARTICLE_LIST_STATE.sort) {
    params.set('sort', state.sort);
  }
  if (state.page > 1) {
    params.set('page', String(state.page));
  }
  return params;
}

export function buildArticleListApiParams(state: ArticleListState): URLSearchParams {
  const params = buildArticleListSearchParams(state);
  params.set('sort', state.sort);
  params.set('limit', String(ARTICLE_PAGE_SIZE));
  params.set('offset', String((state.page - 1) * ARTICLE_PAGE_SIZE));
  return params;
}

export function buildArticleFacetApiParams(state: ArticleListState): URLSearchParams {
  const params = buildArticleListSearchParams({ ...state, page: 1 });
  params.delete('page');
  params.delete('sort');
  params.set('limit', '100');
  return params;
}
