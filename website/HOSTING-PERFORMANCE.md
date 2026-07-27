# Hosting-Feinschliff für vocavid.de

Die Lighthouse-Warnungen **Modern HTTP**, **Cache lifetimes** und ein Teil von **Document request latency** werden vom Webserver/CDN verursacht, nicht von der HTML-Datei.

## Wenn der Webspace Apache oder LiteSpeed nutzt

Die mitgelieferte [`.htaccess`](.htaccess) in den Webroot hochladen. Sie setzt lange Cache-Zeiten für versionierte statische Dateien, kurze Cache-Zeiten für HTML und Kompression für Text-Dateien.

## Wenn der Server Nginx nutzt

Der Hoster sollte für die Website mindestens HTTP/2 und idealerweise HTTP/3 aktivieren sowie für statische Dateien folgende Header ausliefern:

```nginx
location ~* \.(css|js|svg|png|webp|mp4|json)$ {
  expires 1y;
  add_header Cache-Control "public, max-age=31536000, immutable";
}
location = /index.html {
  return 301 /;
}
location ~* \.html$ {
  add_header Cache-Control "public, max-age=0, must-revalidate";
}
```

Nach dem Upload erneut mit Lighthouse im Inkognito-Fenster messen. Falls weiterhin mehrere hundert KB „unused JavaScript“ erscheinen, im Lighthouse-Eintrag **Third parties** nachsehen: Das kann nicht aus VocaVids 1,8-KB-`site.js` stammen und ist dann ein Script des Hosters oder eines eingebundenen Dienstes.
