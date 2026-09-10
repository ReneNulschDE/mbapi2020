const openedFlows = new Set();

function maybeOpenChinaOauth(flowId, url) {
  if (!flowId || !url) {
    return;
  }
  const key = `${flowId}:${url}`;
  if (openedFlows.has(key)) {
    return;
  }
  openedFlows.add(key);
  window.open(url, "_blank", "noopener,noreferrer");
}

function waitForHass() {
  return new Promise((resolve) => {
    const poll = () => {
      const root = document.querySelector("home-assistant");
      if (root && root.hass && root.hass.connection) {
        resolve(root.hass);
        return;
      }
      window.setTimeout(poll, 100);
    };
    poll();
  });
}

async function openChinaOauthFlows(hass) {
  let flows;
  try {
    flows = await hass.callWS({ type: "config_entries/flow/progress" });
  } catch (_err) {
    return;
  }

  for (const flow of flows) {
    if (flow.handler !== "mbapi2020") {
      continue;
    }
    let step;
    try {
      step = await hass.callApi(
        "GET",
        `config/config_entries/flow/${flow.flow_id}`
      );
    } catch (_err) {
      continue;
    }
    if (step.type !== "progress" || step.step_id !== "china_oauth") {
      continue;
    }
    maybeOpenChinaOauth(step.flow_id, step.description_placeholders?.verify_url);
  }
}

waitForHass().then((hass) => {
  hass.connection.subscribeEvents((event) => {
    if (!event || event.event_type !== "mbapi2020_open_china_oauth") {
      return;
    }
    const { flow_id: flowId, url } = event.data || {};
    maybeOpenChinaOauth(flowId, url);
  }, "mbapi2020_open_china_oauth");

  hass.connection.subscribeEvents((event) => {
    if (!event || event.event_type !== "data_entry_flow_progressed") {
      return;
    }
    if (event.data?.handler === "mbapi2020") {
      openChinaOauthFlows(hass);
    }
  }, "data_entry_flow_progressed");

  openChinaOauthFlows(hass);

  const persistMs = 180000;
  const pollMs = 500;
  const maxPolls = Math.ceil(persistMs / pollMs);
  let polls = 0;
  const pollId = window.setInterval(() => {
    openChinaOauthFlows(hass);
    polls += 1;
    if (polls >= maxPolls) {
      window.clearInterval(pollId);
    }
  }, pollMs);
});
