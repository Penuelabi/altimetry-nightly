// Earth Engine app: Nile pulse countdown from Lake Victoria (paste into the app script, then call addNilePulsePanel(Map)).
// Edit SIGNAL when there is a new signal (same date as data/lake_victoria_pulse.json in the repo).
var SIGNAL = '2026-09-20';
var TO_NIMULE = 103;   // days, Lake Victoria to Nimule
var TO_JUBA = 112;     // days, Lake Victoria to Rejaf (Juba): 103 + 9

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
  map.add(panel);
}
// addNilePulsePanel(Map);
