function editMaintenanceRow(row){if(row.classList.contains('editing'))return;row.classList.add('editing');row.querySelectorAll('.maintenance-editor').forEach(function(input){input.disabled=false;});row.querySelectorAll('.maintenance-value').forEach(function(value){value.hidden=true;});var save=row.querySelector('.maintenance-save');if(save){save.disabled=false;}var first=row.querySelector('input.maintenance-editor');if(first)first.focus();}
function updateCatalogType(type){
  var form = document.getElementById('catalogSettingsForm');
  form.action = '/community/catalog/' + type;
  document.getElementById('catalog_type').value = type;

  var locationWrap = document.getElementById('catalog_location_wrap');
  var severityWrap = document.getElementById('catalog_severity_wrap');
  locationWrap.classList.toggle('hidden-field', type !== 'laboratory');
  severityWrap.classList.toggle('hidden-field', type !== 'priority');

  var title = document.getElementById('catalogSettingsTitle');
  title.textContent = type.charAt(0).toUpperCase() + type.slice(1) + ' settings';
}
function openCatalogSettings(row){
  var type = row.dataset.type;
  var recordId = row.dataset.recordId || '';
  document.getElementById('catalog_type_selector').value = type;
  updateCatalogType(type);

  var form = document.getElementById('catalogSettingsForm');
  form.action = '/community/catalog/' + type;
  document.getElementById('catalog_record_id').value = recordId;
  document.getElementById('catalog_name').value = row.dataset.name || '';
  document.getElementById('catalog_description').value = row.dataset.description || '';
  document.getElementById('catalog_location').value = row.dataset.location || '';
  document.getElementById('catalog_severity_level').value = row.dataset.severityLevel || '';

  var modal = document.getElementById('catalogSettingsModal');
  modal.classList.remove('hidden');
}
function closeCatalogSettings(){
  document.getElementById('catalogSettingsModal').classList.add('hidden');
}
function resetCatalogForm(){
  var form = document.getElementById('catalogSettingsForm');
  form.reset();
  document.getElementById('catalog_record_id').value = '';
  document.getElementById('catalog_type').value = '';
  document.getElementById('catalog_type_selector').value = 'category';
  updateCatalogType('category');
  form.action = '/community/catalog/category';
  document.getElementById('catalogSettingsTitle').textContent = 'New catalog item';
  document.getElementById('catalogSettingsModal').classList.remove('hidden');
}
window.addEventListener('keydown', function(event){
  if (event.key === 'Escape') closeCatalogSettings();
});

(function(){var today=new Date().toLocaleDateString('en-CA');document.querySelectorAll('input[type="date"][name="expected_return_date"]').forEach(function(i){i.min=today})})()

document.querySelectorAll('.maintenance-edit-row').forEach(function (row) {
    row.addEventListener('dblclick', function () { editMaintenanceRow(row); });
});
document.querySelectorAll('.catalog-row').forEach(function (row) {
    row.addEventListener('dblclick', function () { openCatalogSettings(row); });
});
document.querySelectorAll('[data-action="close-catalog"]').forEach(function (el) {
    el.addEventListener('click', closeCatalogSettings);
});
document.querySelectorAll('[data-action="reset-catalog"]').forEach(function (el) {
    el.addEventListener('click', resetCatalogForm);
});

document.getElementById('catalog_type_selector').addEventListener('change', function () {
    updateCatalogType(this.value);
});
