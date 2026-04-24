import { useCallback, useEffect, useMemo, useRef, useState } from 'react';

interface SelectableItem {
  id: string;
}

export function useCrossPageSelection<T extends SelectableItem>(
  scopeKey: string,
  pageItems: T[],
) {
  const [selectedIdsSet, setSelectedIdsSet] = useState<Set<string>>(new Set());
  const [selectedItemsMap, setSelectedItemsMap] = useState<Map<string, T>>(new Map());
  const selectedIdsRef = useRef(selectedIdsSet);

  useEffect(() => {
    selectedIdsRef.current = selectedIdsSet;
  }, [selectedIdsSet]);

  const clearSelection = useCallback(() => {
    setSelectedIdsSet(new Set());
    setSelectedItemsMap(new Map());
  }, []);

  useEffect(() => {
    clearSelection();
  }, [clearSelection, scopeKey]);

  useEffect(() => {
    if (pageItems.length === 0 || selectedIdsSet.size === 0) return;
    setSelectedItemsMap((prev) => {
      let next = prev;
      pageItems.forEach((item) => {
        if (!selectedIdsSet.has(item.id)) return;
        if (next.get(item.id) === item) return;
        if (next === prev) next = new Map(prev);
        next.set(item.id, item);
      });
      return next;
    });
  }, [pageItems, selectedIdsSet]);

  const pageIds = useMemo(() => pageItems.map((item) => item.id), [pageItems]);
  const pageSelectedCount = useMemo(
    () => pageIds.filter((id) => selectedIdsSet.has(id)).length,
    [pageIds, selectedIdsSet],
  );
  const allOnPageSelected = pageIds.length > 0 && pageSelectedCount === pageIds.length;
  const someOnPageSelected = pageSelectedCount > 0;

  const toggleOne = useCallback((item: T) => {
    setSelectedIdsSet((prev) => {
      const next = new Set(prev);
      if (next.has(item.id)) next.delete(item.id);
      else next.add(item.id);
      return next;
    });
    setSelectedItemsMap((prev) => {
      const next = new Map(prev);
      if (next.has(item.id)) next.delete(item.id);
      else next.set(item.id, item);
      return next;
    });
  }, []);

  const toggleAllOnPage = useCallback(() => {
    setSelectedIdsSet((prev) => {
      const next = new Set(prev);
      if (pageIds.length > 0 && pageIds.every((id) => prev.has(id))) {
        pageIds.forEach((id) => next.delete(id));
      } else {
        pageIds.forEach((id) => next.add(id));
      }
      return next;
    });
    setSelectedItemsMap((prev) => {
      const next = new Map(prev);
      if (pageItems.length > 0 && pageItems.every((item) => selectedIdsSet.has(item.id))) {
        pageItems.forEach((item) => next.delete(item.id));
      } else {
        pageItems.forEach((item) => next.set(item.id, item));
      }
      return next;
    });
  }, [pageIds, pageItems, selectedIdsSet]);

  const isSelected = useCallback(
    (id: string) => selectedIdsSet.has(id),
    [selectedIdsSet],
  );

  const upsertItem = useCallback(
    (item: T) => {
      if (!selectedIdsRef.current.has(item.id)) return;
      setSelectedItemsMap((prev) => {
        const next = new Map(prev);
        next.set(item.id, item);
        return next;
      });
    },
    [],
  );

  const selectedIds = useMemo(() => Array.from(selectedIdsSet), [selectedIdsSet]);
  const selectedItems = useMemo(
    () =>
      selectedIds
        .map((id) => selectedItemsMap.get(id))
        .filter((item): item is T => Boolean(item)),
    [selectedIds, selectedItemsMap],
  );

  return useMemo(
    () => ({
      selectedIds,
      selectedItems,
      selectedCount: selectedIds.length,
      pageSelectedCount,
      allOnPageSelected,
      someOnPageSelected,
      isSelected,
      toggleOne,
      toggleAllOnPage,
      clearSelection,
      upsertItem,
    }),
    [
      selectedIds,
      selectedItems,
      pageSelectedCount,
      allOnPageSelected,
      someOnPageSelected,
      isSelected,
      toggleOne,
      toggleAllOnPage,
      clearSelection,
      upsertItem,
    ],
  );
}
