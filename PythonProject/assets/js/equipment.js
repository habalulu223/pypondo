function filterInventory(){let q=document.getElementById('inventory-filter').value.toLowerCase();document.querySelectorAll('.room-table tbody tr').forEach(r=>r.hidden=!r.dataset.search.toLowerCase().includes(q))}

document.getElementById('inventory-filter').addEventListener('input', filterInventory);
