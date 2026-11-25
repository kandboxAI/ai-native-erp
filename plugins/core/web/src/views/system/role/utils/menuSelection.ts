export interface MenuSelectionNode {
  id: string;
  title: string;
  menu_type_code: string;
  synthetic?: boolean;
  children: MenuSelectionNode[];
}

function subtree(node: MenuSelectionNode): MenuSelectionNode[] {
  return [node, ...node.children.flatMap(subtree)];
}

/** 目录只承载导航；页面及空目录的直接授权也参与勾选状态。 */
export function menuCheckState(node: MenuSelectionNode, selected: string[]) {
  const ids = new Set(selected);
  const nodes = subtree(node);
  const targets = nodes.filter(
    item => !item.synthetic && (item.menu_type_code !== "directory" || !item.children.length)
  );
  const checked = targets.every(item => ids.has(item.id));
  return {
    checked,
    indeterminate: !checked && targets.some(item => ids.has(item.id))
  };
}

/** 用户勾选目录时处理整棵子树，不修改其他目录的授权。 */
export function toggleMenuSubtree(
  selected: string[],
  node: MenuSelectionNode,
  checked: boolean
): string[] {
  const ids = new Set(selected);
  for (const item of subtree(node)) {
    if (item.synthetic) continue;
    if (checked) ids.add(item.id);
    else ids.delete(item.id);
  }
  return [...ids];
}
