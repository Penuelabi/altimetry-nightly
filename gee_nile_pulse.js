// Earth Engine app: Nile pulse countdown from Lake Victoria (paste into the app script, then call addNilePulsePanel(Map)).
// Edit SIGNAL when there is a new signal (same date as data/lake_victoria_pulse.json in the repo).
var SIGNAL = '2026-09-20';
var TO_NIMULE = 103;   // days, Lake Victoria to Nimule
var TO_JUBA = 112;     // days, Lake Victoria to Rejaf (Juba): 103 + 9
// Second clock: when Lake Victoria reaches the May 2023 mean level (1136.12 m, DAHITI 2), a new 30-day countdown to Juba starts.
// Set LEVEL_TRIGGER_DATE (YYYY-MM-DD) from the report when the "DOUBLE ALERT" appears; leave null while the lake is below the level.
var LEVEL_TRIGGER_DATE = null;
var LEVEL_COUNTDOWN = 30;

function addNilePulsePanel(map) {
  var start = new Date(SIGNAL + 'T00:00:00Z').getTime();
  var today = new Date();
  var day = 86400000;
  function row(name, days) {
    var when = new Date(start + days * day);
    var left = Math.ceil((when.getTime() - today.getTime()) / day);
    var color = left < 0 ? '#555555' : left <= 10 ? '#b00020' : left <= 30 ? '#b36b00' : '#1a6e3c';
    var txt = left < 0 ? 'expected ' + when.toISOString().slice(0, 10) + ' (' + (-left) + ' days ago)'
                       : left + ' days left, expected ' + when.toISOString().slice(0, 10);
    return ui.Label(name + ': ' + txt, {color: color, fontWeight: 'bold', fontSize: '12px', margin: '2px 8px'});
  }
  var panel = ui.Panel({style: {position: 'bottom-left', padding: '6px', width: '300px'}});
  panel.add(ui.Label('Nile pulse countdown from Lake Victoria', {fontWeight: 'bold', fontSize: '13px', margin: '2px 8px'}));
  panel.add(ui.Label('Clock started ' + SIGNAL + '. Travel-time estimate, not a river-level forecast.',
                     {fontSize: '10px', color: '#666666', margin: '0 8px 4px 8px'}));
  panel.add(row('Nimule', TO_NIMULE));
  panel.add(row('Juba (Rejaf)', TO_JUBA));
  if (LEVEL_TRIGGER_DATE) {
    var t0 = new Date(LEVEL_TRIGGER_DATE + 'T00:00:00Z').getTime();
    panel.add(ui.Label('DOUBLE ALERT: Lake Victoria reached the May 2023 level on ' + LEVEL_TRIGGER_DATE,
                       {color: '#b00020', fontWeight: 'bold', fontSize: '11px', margin: '4px 8px 0 8px'}));
    var w2 = new Date(t0 + LEVEL_COUNTDOWN * day);
    var l2 = Math.ceil((w2.getTime() - today.getTime()) / day);
    panel.add(ui.Label('Juba (new 30-day clock): ' + (l2 < 0 ? 'expected ' + w2.toISOString().slice(0, 10) : l2 + ' days left, expected ' + w2.toISOString().slice(0, 10)),
                       {color: l2 <= 10 ? '#b00020' : '#b36b00', fontWeight: 'bold', fontSize: '12px', margin: '2px 8px'}));
  }
  map.add(panel);
}
// addNilePulsePanel(Map);
