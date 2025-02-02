import { ArrowDropDown as ArrowDropDownIcon, Close as CloseIcon } from "@mui/icons-material";
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  ClickAwayListener,
  Grow,
  IconButton,
  MenuItem,
  MenuList,
  Paper,
  Popper,
  TextField,
  Typography,
} from "@mui/material";
import { DateTimePicker, LocalizationProvider } from "@mui/x-date-pickers";
import { AdapterDateFns } from "@mui/x-date-pickers/AdapterDateFns";
import { isBefore } from "date-fns";
import { useSnackbar } from "notistack";
import PropTypes from "prop-types";
import React, { useRef, useState } from "react";
import { useDispatch } from "react-redux";

import dialogStyle from "../cssModule/dialog.module.css";
import {
  getPTeamServiceTaggedTopicIds,
  getPTeamServiceTagsSummary,
  getPTeamTagsSummary,
  getTicketsRelatedToServiceTopicTag,
} from "../slices/pteam";
import { setTicketStatus } from "../utils/api";
import { topicStatusProps } from "../utils/const";
import { dateTimeFormat } from "../utils/func";

export function TopicStatusSelector(props) {
  const { pteamId, serviceId, topicId, tagId, ticketId, currentStatus } = props;

  const [open, setOpen] = useState(false);
  const anchorRef = useRef(null);
  const [datepickerOpen, setDatepickerOpen] = useState(false);
  const [schedule, setSchedule] = useState(null); // Date object

  const { enqueueSnackbar } = useSnackbar();
  const dispatch = useDispatch();

  const dateFormat = "yyyy/MM/dd HH:mm";
  const selectableItems = [
    {
      display: "Acknowledge",
      rawStatus: "acknowledged",
      disabled: currentStatus.topic_status === "acknowledged",
    },
    { display: "Schedule", rawStatus: "scheduled", disabled: false },
  ];

  const modifyTicketStatus = async (selectedStatus) => {
    let requestParams = { topic_status: selectedStatus };
    if (selectedStatus === "scheduled") {
      if (!schedule) return;
      requestParams["scheduled_at"] = schedule.toISOString();
    }
    await setTicketStatus(pteamId, serviceId, ticketId, requestParams)
      .then(() => {
        dispatch(
          getTicketsRelatedToServiceTopicTag({
            pteamId: pteamId,
            serviceId: serviceId,
            topicId: topicId,
            tagId: tagId,
          }),
        );
        dispatch(getPTeamServiceTagsSummary({ pteamId: pteamId, serviceId: serviceId }));
        dispatch(getPTeamTagsSummary({ pteamId: pteamId }));
        dispatch(
          getPTeamServiceTaggedTopicIds({
            pteamId: pteamId,
            serviceId: serviceId,
            tagId: tagId,
          }),
        );
        enqueueSnackbar("Change ticket status succeeded", { variant: "success" });
      })
      .catch((error) => {
        const resp = error.response;
        enqueueSnackbar(
          `Operation failed: ${resp.status} ${resp.statusText} - ${resp.data?.detail}`,
          { variant: "error" },
        );
      });
  };
  const handleUpdateStatus = async (event, item) => {
    setOpen(false);
    if (item.rawStatus === "scheduled") {
      setDatepickerOpen(true);
      return;
    }
    modifyTicketStatus(item.rawStatus);
  };
  const handleUpdateSchedule = async () => {
    setDatepickerOpen(false);
    modifyTicketStatus("scheduled");
  };

  const handleClose = (event) => {
    if (anchorRef.current?.contains(event.target)) return;
    setOpen(false);
  };

  if (!pteamId || !serviceId || !topicId || !tagId || !currentStatus) return <></>;

  const handleHideDatepicker = () => {
    setSchedule(currentStatus.scheduled_at ? dateTimeFormat(currentStatus.scheduled_at) : null);
    setDatepickerOpen(false);
  };
  const now = new Date();

  return (
    <>
      <Button
        endIcon={<ArrowDropDownIcon />}
        sx={{
          ...topicStatusProps[currentStatus.topic_status].buttonStyle,
          fontSize: 12,
          padding: "1px 3px",
          minHeight: "25px",
          maxHeight: "25px",
          textTransform: "none",
          fontWeight: 900,
          borderStyle: "none",
          mr: 1,
          "&:hover": {
            borderStyle: "none",
          },
        }}
        aria-controls={open ? "status-menu" : undefined}
        aria-expanded={open ? "true" : undefined}
        aria-haspopup="menu"
        onClick={() => setOpen(!open)}
        ref={anchorRef}
      >
        {topicStatusProps[currentStatus.topic_status].chipLabelCapitalized}
      </Button>
      <Popper
        open={open}
        anchorEl={anchorRef.current}
        role={undefined}
        transition
        disablePortal
        sx={{ zIndex: 1 }}
      >
        {({ TransitionProps, placement }) => (
          <Grow
            {...TransitionProps}
            style={{
              transformOrigin: placement === "bottom" ? "center top" : "center bottom",
            }}
          >
            <Paper>
              <ClickAwayListener onClickAway={handleClose}>
                <MenuList autoFocusItem>
                  {selectableItems.map((item) => (
                    <MenuItem
                      key={item.rawStatus}
                      selected={currentStatus.topic_status === item.rawStatus}
                      disabled={item.disabled}
                      onClick={(event) => handleUpdateStatus(event, item)}
                      dense={true}
                    >
                      {item.display}
                    </MenuItem>
                  ))}
                </MenuList>
              </ClickAwayListener>
            </Paper>
          </Grow>
        )}
      </Popper>
      <Dialog open={datepickerOpen} onClose={handleHideDatepicker} fullWidth>
        <DialogTitle>
          <Box alignItems="center" display="flex" flexDirection="row">
            <Typography flexGrow={1} className={dialogStyle.dialog_title}>
              Set schedule
            </Typography>
            <IconButton onClick={handleHideDatepicker}>
              <CloseIcon />
            </IconButton>
          </Box>
        </DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 3 }}>
            <LocalizationProvider dateAdapter={AdapterDateFns}>
              <DateTimePicker
                inputFormat={dateFormat}
                label="Schedule Date (future date)"
                mask="____/__/__ __:__"
                minDateTime={now}
                value={schedule}
                onChange={(newDate) => setSchedule(newDate)}
                renderInput={(params) => (
                  <TextField fullWidth margin="dense" required {...params} />
                )}
                sx={{ width: "100%" }}
              />
            </LocalizationProvider>
          </Box>
        </DialogContent>
        <DialogActions className={dialogStyle.action_area}>
          <Button
            onClick={handleUpdateSchedule}
            disabled={!isBefore(now, schedule)}
            className={dialogStyle.submit_btn}
          >
            Schedule
          </Button>
        </DialogActions>
      </Dialog>
    </>
  );
}

TopicStatusSelector.propTypes = {
  pteamId: PropTypes.string.isRequired,
  serviceId: PropTypes.string.isRequired,
  topicId: PropTypes.string.isRequired,
  tagId: PropTypes.string.isRequired,
  ticketId: PropTypes.string.isRequired,
  currentStatus: PropTypes.object.isRequired,
};
