'use strict';
// F1: minimal service worker for installability. Offline feeds are deferred to F4.
self.addEventListener('install',()=>self.skipWaiting());
self.addEventListener('activate',event=>event.waitUntil(self.clients.claim()));
self.addEventListener('fetch',()=>{});
