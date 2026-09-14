(function (root, factory) {
  'use strict';
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  else root.SteeringCues = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';
  const normal = value => String(value || '').toLowerCase();
  function style(effect, actions = []) {
    const action = [...actions].reverse().find(item => {
      const age = effect.changedAt - Date.parse(item.requested_at || '');
      return normal(item.sta_mac) === normal(effect.staMAC) && effect.fromBSSID && effect.toBSSID &&
        normal(item.source_bssid) === normal(effect.fromBSSID) && normal(item.target_bssid) === normal(effect.toBSSID) &&
        age >= -1000 && age <= 30000;
    });
    if (action?.method === 'btm-request') return {method: 'btm', color: '#0f766e', label: 'BTM request'};
    if (action?.method === 'non-btm' && action.evidence === 'operator-report') return {method: 'non-btm', color: '#be185d', label: 'Non-BTM reported'};
    return {method: 'unknown', color: '#64748b', label: 'Method unknown'};
  }

  function draw(group, effect, sourceNode, targetNode, staData, clientName, actions, zoomScale = 1) {
    const appearance = style(effect, actions);
    const cue = group.append('g').datum({effect, sourceNode, targetNode, staData, clientName})
      .attr('class', 'sta-roam-cue').attr('data-method', appearance.method)
      .attr('aria-label', `${clientName}: ${effect.fromOwnerName} to ${effect.toOwnerName}; ${appearance.label}`)
      .attr('opacity', Math.max(0, 1 - effect.ageMs / 6000)).style('pointer-events', 'none');
    cue.append('title').text(`${clientName}: ${effect.fromOwnerName} → ${effect.toOwnerName}. ${appearance.label}. The current association is already displayed; this is only a fading history overlay.`);
    cue.append('animate').attr('attributeName', 'opacity').attr('to', 0)
      .attr('dur', `${effect.remainingMs}ms`).attr('fill', 'freeze');
    cue.append('path').attr('class', 'sta-steering-trail').attr('fill', 'none')
      .attr('stroke', appearance.color).attr('stroke-width', 4).attr('stroke-dasharray', '9 7');
    cue.append('path').attr('class', 'sta-roam-arrow').attr('fill', appearance.color);
    cue.append('circle').attr('class', 'sta-roam-source').attr('r', staData.iconSize / 2 + 5)
      .attr('fill', '#fff').attr('fill-opacity', 0.6).attr('stroke', appearance.color)
      .attr('stroke-width', 3).attr('stroke-dasharray', '4 4');
    const fontSize = Math.min(32, Math.max(18, 12 / zoomScale));
    const label = cue.append('text').attr('class', 'sta-roam-origin-label').attr('font-size', fontSize)
      .attr('font-weight', 700).attr('text-anchor', 'middle').attr('fill', appearance.color)
      .attr('stroke', '#fff').attr('stroke-width', 4).attr('paint-order', 'stroke')
      .text(`${clientName} · FROM ${effect.fromOwnerName}`);
    label.append('tspan').attr('class', 'sta-roam-method-label').attr('dy', fontSize + 2).text(appearance.label);
    cue.append('circle').attr('class', 'sta-steer-pulse').attr('r', staData.iconSize / 2 + 7)
      .attr('fill', 'none').attr('stroke', appearance.color).attr('stroke-width', 4);
    position(cue);
    setTimeout(() => cue.remove(), effect.remainingMs);
    return cue;
  }

  function position(cue) {
    const {effect, sourceNode, targetNode, staData} = cue.datum();
    const sourceX = sourceNode ? (sourceNode.fx ?? sourceNode.x) + (effect.sourceOffsetX || 0) : effect.fromX;
    const sourceY = sourceNode ? (sourceNode.fy ?? sourceNode.y) + (effect.sourceOffsetY || 0) : effect.fromY;
    const targetX = (targetNode.fx ?? targetNode.x) + staData.to.x;
    const targetY = (targetNode.fy ?? targetNode.y) + staData.to.y;
    if (![sourceX, sourceY, targetX, targetY].every(Number.isFinite)) { cue.attr('display', 'none'); return; }
    const midX = (sourceX + targetX) / 2, midY = (sourceY + targetY) / 2 - 45;
    cue.select('.sta-steering-trail').attr('d', `M${sourceX},${sourceY} Q${midX},${midY} ${targetX},${targetY}`);
    cue.select('.sta-roam-arrow').attr('d', 'M0,0 L-14,-7 L-14,7 Z')
      .attr('transform', `translate(${targetX},${targetY}) rotate(${Math.atan2(targetY - midY, targetX - midX) * 180 / Math.PI})`);
    cue.select('.sta-roam-source').attr('cx', sourceX).attr('cy', sourceY);
    const label = cue.select('.sta-roam-origin-label');
    label.attr('x', sourceX).attr('y', sourceY - staData.iconSize / 2 - Number(label.attr('font-size')) - 18);
    label.select('.sta-roam-method-label').attr('x', sourceX);
    cue.select('.sta-steer-pulse').attr('cx', targetX).attr('cy', targetY);
  }
  function refresh(cue, actions) {
    const {effect, clientName} = cue.datum();
    const appearance = style(effect, actions);
    if (cue.attr('data-method') === appearance.method) return;
    cue.attr('data-method', appearance.method)
      .attr('aria-label', `${clientName}: ${effect.fromOwnerName} to ${effect.toOwnerName}; ${appearance.label}`);
    cue.selectAll('.sta-steering-trail, .sta-roam-source, .sta-steer-pulse').attr('stroke', appearance.color);
    cue.select('.sta-roam-arrow').attr('fill', appearance.color);
    cue.select('.sta-roam-origin-label').attr('fill', appearance.color);
    cue.select('.sta-roam-method-label').text(appearance.label);
    cue.select('title').text(`${clientName}: ${effect.fromOwnerName} → ${effect.toOwnerName}. ${appearance.label}. History overlay only.`);
  }
  return {style, draw, position, refresh};
});
