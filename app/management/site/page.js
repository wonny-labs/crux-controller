"use strict";
(function () {
  var SESSION = "/api/v1/session";
  var STATUS = "/api/v1/status";
  var POLL_MS = 300;
  var POLL_MAX = 60;

  var form = document.getElementById("login");
  var panel = document.getElementById("status");
  var message = document.getElementById("message");
  var items = document.getElementById("items");
  var who = document.getElementById("who");

  function say(text) {
    message.textContent = text;
  }

  function cookie(name) {
    var parts = document.cookie.split("; ");
    for (var i = 0; i < parts.length; i++) {
      var pair = parts[i].split("=");
      if (pair[0] === name) {
        return pair.slice(1).join("=");
      }
    }
    return "";
  }

  function show(signedIn) {
    form.hidden = signedIn;
    panel.hidden = !signedIn;
  }

  function request(method, path, headers, body) {
    var options = { method: method, headers: headers || {}, credentials: "same-origin" };
    if (body !== undefined) {
      options.body = body;
    }
    return fetch(path, options);
  }

  function wait(ms) {
    return new Promise(function (resolve) {
      setTimeout(resolve, ms);
    });
  }

  function row(name, value) {
    var tr = document.createElement("tr");
    var a = document.createElement("td");
    var b = document.createElement("td");
    a.textContent = name;
    b.textContent = value;
    tr.appendChild(a);
    tr.appendChild(b);
    return tr;
  }

  function loadStatus() {
    return request("GET", STATUS).then(function (response) {
      if (response.status === 401) {
        show(false);
        say("Signed out. Sign in again.");
        return null;
      }
      if (!response.ok) {
        say("The status is not available (" + response.status + ").");
        return null;
      }
      return response.json().then(function (document_) {
        items.textContent = "";
        document_.items.forEach(function (item) {
          var text = item.status === "ok" ? String(item.value) : item.status;
          items.appendChild(row(item.name, text));
        });
        show(true);
        return request("GET", SESSION + "/me").then(function (me) {
          return me.ok ? me.json() : null;
        });
      }).then(function (me) {
        who.textContent = me ? "Signed in as " + me.user + " (" + me.role + ")." : "";
      });
    });
  }

  function poll(id, count) {
    if (count >= POLL_MAX) {
      say("The sign-in did not finish in time.");
      return Promise.resolve();
    }
    return wait(POLL_MS).then(function () {
      return request("GET", SESSION + "/attempt/" + encodeURIComponent(id), { "X-Crux-Request": "1" });
    }).then(function (response) {
      if (response.status === 429) {
        say("Too many attempts. Wait " + (response.headers.get("Retry-After") || "a while") + " seconds.");
        return null;
      }
      if (!response.ok) {
        say("The sign-in failed (" + response.status + ").");
        return null;
      }
      return response.json().then(function (result) {
        if (result.state === "pending") {
          return poll(id, count + 1);
        }
        if (result.state === "success") {
          say("");
          return loadStatus();
        }
        say("The user name or the password was not accepted.");
        return null;
      });
    });
  }

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    var user = form.elements.user.value;
    var body = JSON.stringify({ user: user, password: form.elements.password.value });
    form.elements.password.value = "";
    say("Signing in.");
    request("POST", SESSION, { "Content-Type": "application/json" }, body).then(function (response) {
      if (response.status !== 202) {
        say(response.status === 503 ? "The device is busy. Try again." : "The sign-in was refused (" + response.status + ").");
        return null;
      }
      return response.json().then(function (queued) {
        return poll(queued.id, 0);
      });
    }).catch(function () {
      say("The device did not answer.");
    });
  });

  document.getElementById("refresh").addEventListener("click", function () {
    loadStatus().catch(function () {
      say("The device did not answer.");
    });
  });

  document.getElementById("logout").addEventListener("click", function () {
    request("DELETE", SESSION, { "X-XSRF-TOKEN": cookie("XSRF-TOKEN") }).then(function () {
      items.textContent = "";
      show(false);
      say("Signed out.");
    }).catch(function () {
      say("The device did not answer.");
    });
  });

  show(false);
})();
