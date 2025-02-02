import { Close as CloseIcon } from "@mui/icons-material";
import {
  Box,
  Button,
  Dialog,
  DialogContent,
  DialogTitle,
  IconButton,
  TextField,
  Typography,
  MenuItem,
} from "@mui/material";
import { grey } from "@mui/material/colors";
import { useSnackbar } from "notistack";
import PropTypes from "prop-types";
import React, { useState } from "react";
import { useDispatch, useSelector } from "react-redux";
import { useParams } from "react-router-dom";

import dialogStyle from "../cssModule/dialog.module.css";
import {
  getTopicStatus,
  getPTeamServiceTaggedTopicIds,
  getPTeamServiceTagsSummary,
  getPTeamTagsSummary,
} from "../slices/pteam";
import { createActionLog, createTopicStatus } from "../utils/api";

import { ActionTypeChip } from "./ActionTypeChip";
import { ActionTypeIcon } from "./ActionTypeIcon";
import { RecommendedStar } from "./RecommendedStar";
import { UUIDTypography } from "./UUIDTypography";

export function ReportCompletedActions(props) {
  const { onConfirm, onSetShow, show, topicId, topicActions, serviceId } = props;

  const [note, setNote] = useState("");
  const [selectedAction, setSelectedAction] = useState([]);
  const [activeStep, setActiveStep] = useState(0);
  const [skipped, setSkipped] = useState(new Set());

  const { tagId } = useParams();
  const { enqueueSnackbar } = useSnackbar();

  const pteamId = useSelector((state) => state.pteam.pteamId);
  const topics = useSelector((state) => state.topics.topics); // dispatched by parent
  const user = useSelector((state) => state.user.user);

  const dispatch = useDispatch();

  const handleAction = async () => {
    try {
      const actionLogs = await Promise.all(
        selectedAction.map(
          async (actionId) =>
            await createActionLog({
              action_id: actionId,
              pteam_id: pteamId,
              service_id: serviceId,
              topic_id: topicId,
              user_id: user.user_id,
            }).then((response) => {
              enqueueSnackbar("Action succeeded", { variant: "success" });
              return response.data;
            }),
        ),
      );
      await createTopicStatus(pteamId, serviceId, topicId, tagId, {
        topic_status: "completed",
        logging_ids: actionLogs.map((logs) => logs.map((log) => log.logging_id)).flat(),
        note: note.trim() || null,
      });
      handleClose();
      onConfirm();
      setNote("");
      dispatch(
        getTopicStatus({ pteamId: pteamId, serviceId: serviceId, topicId: topicId, tagId: tagId }),
      );
      dispatch(
        getPTeamServiceTaggedTopicIds({ pteamId: pteamId, serviceId: serviceId, tagId: tagId }),
      );
      dispatch(getPTeamServiceTagsSummary({ pteamId: pteamId, serviceId: serviceId }));
      dispatch(getPTeamTagsSummary({ pteamId: pteamId }));
      enqueueSnackbar("Set topicstatus 'completed' succeeded", { variant: "success" });
    } catch (error) {
      enqueueSnackbar(`Operation failed: ${error}`, { variant: "error" });
    }
  };

  if (!pteamId || !topicId || !topics[topicId] || !topicActions) return <></>;

  const handleClose = () => {
    onSetShow(false);
  };

  const handleSelectAction = async (actionId) => {
    if (!actionId) {
      if (selectedAction.length) setSelectedAction([]);
      else setSelectedAction(topicActions.map((action) => action.action_id));
    } else {
      if (selectedAction.includes(actionId))
        selectedAction.splice(selectedAction.indexOf(actionId), 1);
      else selectedAction.push(actionId);
      setSelectedAction([...selectedAction]);
    }
  };

  const isStepSkipped = (step) => {
    return skipped.has(step);
  };

  const handleNext = () => {
    let newSkipped = skipped;
    if (isStepSkipped(activeStep)) {
      newSkipped = new Set(newSkipped.values());
      newSkipped.delete(activeStep);
    }
    setActiveStep((prevActiveStep) => prevActiveStep + 1);
    setSkipped(newSkipped);
  };

  const handleBack = () => {
    setActiveStep((prevActiveStep) => prevActiveStep - 1);
  };

  return (
    <Dialog open={show} onClose={handleClose} fullWidth>
      <DialogTitle>
        <Box alignItems="center" display="flex" flexDirection="row">
          {activeStep === 0 && (
            <Typography flexGrow={1} className={dialogStyle.dialog_title}>
              Select the actions you have completed
            </Typography>
          )}
          {activeStep === 1 && (
            <Typography flexGrow={1} className={dialogStyle.dialog_title}>
              (Optional): Enter evidence of completion
            </Typography>
          )}
          <IconButton onClick={handleClose}>
            <CloseIcon />
          </IconButton>
        </Box>
      </DialogTitle>
      <DialogContent>
        {activeStep === 0 && (
          <>
            {topicActions.length === 0 ? (
              <Box display="flex" flexDirection="row" alignItems="center" sx={{ color: grey[500] }}>
                <Typography variant="body2">No action</Typography>
              </Box>
            ) : (
              <>
                {topicActions.map((action) => (
                  <MenuItem
                    key={action.action_id}
                    onClick={() => handleSelectAction(action.action_id)}
                    selected={selectedAction.includes(action.action_id)}
                    sx={{
                      alignItems: "center",
                      display: "flex",
                      flexDirection: "row",
                    }}
                  >
                    <ActionTypeIcon
                      disabled={!action.recommended}
                      actionType={action.action_type}
                    />
                    <Box display="flex" flexDirection="column">
                      <Typography noWrap variant="body" width={400}>
                        {action.action}
                      </Typography>
                      <UUIDTypography>{action.action_id}</UUIDTypography>
                    </Box>
                  </MenuItem>
                ))}
              </>
            )}
          </>
        )}
        {activeStep === 1 && (
          <>
            {topics[topicId]?.actions &&
              topics[topicId].actions
                .filter((action) => selectedAction.includes(action.action_id))
                .map((action) => (
                  <Box
                    alignItems="center"
                    display="flex"
                    flexDirection="row"
                    key={action.action_id}
                    mb={1}
                  >
                    <ActionTypeChip actionType={action.action_type} />
                    <RecommendedStar disabled={!action.recommended} />
                    <Box display="flex" flexDirection="column">
                      <Typography>{action.action}</Typography>
                      <UUIDTypography>{action.action_id}</UUIDTypography>
                    </Box>
                  </Box>
                ))}
            <TextField
              fullWidth
              multiline
              onChange={(event) => setNote(event.target.value)}
              placeholder={
                "Evidence that you have completed the action, such as a report URL, " +
                "event logs, file hashes, etc."
              }
              variant="outlined"
              value={note}
            />
          </>
        )}
        <Box sx={{ display: "flex", flexDirection: "row", pt: 2 }}>
          {activeStep === 0 ? (
            <>
              <Box sx={{ flex: "1 1 auto" }} />
              <Button
                onClick={handleNext}
                className={dialogStyle.submit_btn}
                disabled={selectedAction.length === 0}
              >
                {`Done ${selectedAction.length}`}
              </Button>
            </>
          ) : (
            <>
              <Button
                onClick={handleBack}
                className={dialogStyle.submit_btn}
                disabled={activeStep === 0}
                sx={{ ml: -2 }}
              >
                Back
              </Button>
              <Box sx={{ flex: "1 1 auto" }} />
              <Button onClick={handleAction} className={dialogStyle.submit_btn}>
                Submit
              </Button>
            </>
          )}
        </Box>
      </DialogContent>
    </Dialog>
  );
}

ReportCompletedActions.propTypes = {
  onConfirm: PropTypes.func.isRequired,
  onSetShow: PropTypes.func.isRequired,
  show: PropTypes.bool.isRequired,
  topicId: PropTypes.string.isRequired,
  topicActions: PropTypes.array.isRequired,
  serviceId: PropTypes.string.isRequired,
};
